"""Tests for the MOSAIC web UI routes."""
from __future__ import annotations

import time
from unittest.mock import patch, MagicMock

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
    defaults = dict(
        title="Test Paper", authors=["Author A"], year=2024,
        doi="10.1234/test", source="arXiv", is_open_access=True,
        pdf_url="https://example.com/test.pdf",
    )
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
        resp = client.post("/config",
                           data={"download_dir": "/tmp/test"},
                           headers={"HX-Request": "true"})
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


class TestStreamEndpoint:
    def test_stream_unknown_job(self, client):
        resp = client.get("/stream/nonexistent")
        assert resp.status_code == 200
        assert b"event: done" in resp.data
