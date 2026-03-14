"""Tests for the MOSAIC web UI routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mosaic.models import Paper

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path):
    """Create a Flask test app with an in-memory-like temp DB."""
    from mosaic.ui import create_app

    with patch("mosaic.config.load") as mock_load:
        mock_load.return_value = {
            "db_path": str(tmp_path / "test.db"),
            "download_dir": str(tmp_path / "downloads"),
            "filename_pattern": "{year}_{source}_{author}_{title}",
            "sources": {},
            "unpaywall": {"email": ""},
            "zotero": {},
        }
        flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _make_paper(**kw):
    defaults = {
        "title": "Test Paper",
        "authors": ["Author A"],
        "year": 2024,
        "doi": "10.1234/test",
        "source": "arXiv",
        "is_open_access": True,
        "pdf_url": "https://example.com/test.pdf",
    }
    defaults.update(kw)
    return Paper(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPages:
    def test_search_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"MOSAIC" in resp.data

    def test_similar_page(self, client):
        resp = client.get("/similar")
        assert resp.status_code == 200
        assert b"Similar" in resp.data

    def test_history_page(self, client):
        resp = client.get("/history")
        assert resp.status_code == 200
        assert b"History" in resp.data

    def test_config_page(self, client):
        resp = client.get("/config")
        assert resp.status_code == 200
        assert b"Configuration" in resp.data


class TestSearch:
    def test_empty_query(self, client):
        resp = client.post("/search", data={"query": ""})
        assert resp.status_code == 200
        assert b"Please enter a search query" in resp.data

    @patch("mosaic.ui.routes.build_sources")
    @patch("mosaic.ui.routes.search_all")
    def test_search_submit_and_status(self, mock_search, mock_build, client, app):
        papers = [_make_paper()]
        mock_search.return_value = papers
        mock_build.return_value = []

        # Submit search
        resp = client.post("/search", data={"query": "test", "max_results": "5"})
        assert resp.status_code == 200
        # Should return a job_status partial with polling
        assert b"hx-get" in resp.data or b"hx-trigger" in resp.data

    def test_search_status_not_found(self, client):
        resp = client.get("/search/status/nonexistent")
        assert resp.status_code == 200
        assert b"Job not found" in resp.data


class TestPaperDetail:
    def test_paper_not_found(self, client):
        resp = client.get("/paper/nonexistent", follow_redirects=True)
        assert resp.status_code == 200

    def test_paper_found(self, client, app):
        paper = _make_paper()
        with app.app_context():
            from flask import current_app

            current_app.config["MOSAIC_CACHE"].save(paper)

        resp = client.get(f"/paper/{paper.uid}")
        assert resp.status_code == 200
        assert b"Test Paper" in resp.data


class TestDownload:
    def test_download_not_found(self, client):
        resp = client.post("/download/nonexistent")
        assert resp.status_code == 404

    def test_download_submits_job(self, client, app):
        paper = _make_paper()
        with app.app_context():
            from flask import current_app

            current_app.config["MOSAIC_CACHE"].save(paper)

        resp = client.post(f"/download/{paper.uid}")
        assert resp.status_code == 200
        assert b"Downloading" in resp.data


class TestConfig:
    def test_config_save_htmx(self, client):
        resp = client.post(
            "/config", data={"download_dir": "/tmp/test"}, headers={"HX-Request": "true"}
        )
        assert resp.status_code == 200
        assert b"Configuration saved" in resp.data


class TestHistory:
    def test_history_empty(self, client):
        resp = client.get("/history")
        assert resp.status_code == 200
        assert b"No searches yet" in resp.data

    def test_history_with_entries(self, client, app):
        with app.app_context():
            from flask import current_app

            cache = current_app.config["MOSAIC_CACHE"]
            cache.save_search("transformers", result_count=42)

        resp = client.get("/history")
        assert resp.status_code == 200
        assert b"transformers" in resp.data
        assert b"42" in resp.data

    def test_history_rerun_prefills_query(self, client, app):
        """Re-run link should navigate to search page with query pre-filled."""
        with app.app_context():
            from flask import current_app

            cache = current_app.config["MOSAIC_CACHE"]
            cache.save_search("attention is all you need", result_count=15)

        # History page should contain a link with ?q=...
        resp = client.get("/history")
        assert b"?q=attention" in resp.data

        # Following the link should render the search page with value filled
        resp2 = client.get("/?q=attention+is+all+you+need")
        assert resp2.status_code == 200
        assert b'value="attention is all you need"' in resp2.data
        # Auto-submit script should be present
        assert b"DOMContentLoaded" in resp2.data


class TestExport:
    def test_export_no_results(self, client):
        resp = client.get("/export/nonexistent", follow_redirects=True)
        assert resp.status_code == 200
        assert b"expired" in resp.data

    def test_zotero_export_expired(self, client):
        resp = client.post("/zotero/export/nonexistent")
        assert resp.status_code == 200
        assert b"expired" in resp.data

    def test_obsidian_export_expired(self, client):
        resp = client.post("/obsidian/export/nonexistent")
        assert resp.status_code == 200
        assert b"expired" in resp.data


class TestStreamEndpoint:
    def test_stream_unknown_job(self, client):
        resp = client.get("/stream/nonexistent")
        assert resp.status_code == 200
        assert b"event: done" in resp.data


class TestInputValidation:
    """Tests for input validation edge cases."""

    def test_invalid_year_format_shows_warning(self, client, app):
        """Invalid year filter should warn user, not silently ignore."""
        with (
            patch("mosaic.ui.routes.build_sources") as mock_build,
            patch("mosaic.ui.routes.search_all") as mock_search,
        ):
            mock_build.return_value = [MagicMock(name="arXiv")]
            mock_search.return_value = []

            resp = client.post(
                "/search",
                data={
                    "query": "test",
                    "year": "abc",
                    "max_results": "5",
                },
            )
            assert resp.status_code == 200
            # Should get a polling response; wait for status to see warning
            # The job_meta should contain the year_warning
            with app.app_context():
                from flask import current_app

                _jm = current_app.config["JOB_MANAGER"]
                # Find the stored meta
                meta_keys = [k for k in current_app.config if k.startswith("job_meta_")]
                assert len(meta_keys) == 1
                meta = current_app.config[meta_keys[0]]
                assert "Invalid year format" in meta["year_warning"]

    def test_no_sources_selected_shows_error(self, client):
        """Deselecting all sources should show error, not search all."""
        resp = client.post(
            "/search",
            data={
                "query": "test",
                "_has_sources": "1",
                # No "sources" key — all deselected
            },
        )
        assert resp.status_code == 200
        assert b"No sources selected" in resp.data

    def test_bad_max_results_does_not_crash(self, client, app):
        """Non-numeric max_results should not cause 500 error."""
        with (
            patch("mosaic.ui.routes.build_sources") as mock_build,
            patch("mosaic.ui.routes.search_all") as mock_search,
        ):
            mock_build.return_value = [MagicMock(name="arXiv")]
            mock_search.return_value = []

            resp = client.post(
                "/search",
                data={
                    "query": "test",
                    "max_results": "abc",
                },
            )
            assert resp.status_code == 200

    def test_similar_bad_max_results(self, client, app):
        """Non-numeric max_results on similar page should not crash."""
        with patch("mosaic.ui.routes._run_similar"):
            resp = client.post(
                "/similar",
                data={
                    "identifier": "10.1234/test",
                    "max_results": "not_a_number",
                },
            )
            assert resp.status_code == 200


class TestHistoryFilters:
    """Tests for history filter preservation."""

    def test_history_rerun_preserves_filters(self, client, app):
        """Re-run link should include filter params from the original search."""
        with app.app_context():
            import json

            from flask import current_app

            cache = current_app.config["MOSAIC_CACHE"]
            cache.save_search(
                "neural networks",
                filters_json=json.dumps({"year": "2023", "author": "Smith"}),
                result_count=10,
            )

        resp = client.get("/history")
        assert resp.status_code == 200
        assert b"year=2023" in resp.data
        assert b"author=Smith" in resp.data

    def test_search_page_prefills_filters(self, client):
        """Search page should prefill filter fields from query params."""
        resp = client.get("/?q=test&year=2023&author=Smith&field=title")
        assert resp.status_code == 200
        assert b'value="2023"' in resp.data
        assert b'value="Smith"' in resp.data
