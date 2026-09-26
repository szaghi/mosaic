"""Tests for the NotebookLM bridge module."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mosaic.models import Paper

# ---------------------------------------------------------------------------
# Helpers — inject a fake `notebooklm` package into sys.modules so that
# the bridge can be tested without the real dependency installed.
# ---------------------------------------------------------------------------


def _make_fake_notebooklm(nb_id: str = "nb-001") -> tuple[ModuleType, MagicMock]:
    """Return (fake_module, mock_client_instance)."""
    fake_nb = MagicMock()
    fake_nb.id = nb_id

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.notebooks.create = AsyncMock(return_value=fake_nb)
    client.sources.add_file = AsyncMock()
    client.sources.add_url = AsyncMock()
    client.artifacts.generate_audio = AsyncMock()

    NotebookLMClient = MagicMock()  # noqa: N806
    NotebookLMClient.from_storage = AsyncMock(return_value=client)

    mod = ModuleType("notebooklm")
    mod.NotebookLMClient = NotebookLMClient  # type: ignore[attr-defined]

    return mod, client


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# require_notebooklm
# ---------------------------------------------------------------------------


class TestRequireNotebooklm:
    def test_raises_when_not_installed(self):
        from mosaic.notebooklm_bridge import require_notebooklm

        with patch.dict(sys.modules, {"notebooklm": None}):
            with pytest.raises(ImportError, match="mosaic-search\\[notebooklm\\]"):
                require_notebooklm()

    def test_passes_when_installed(self):
        from mosaic.notebooklm_bridge import require_notebooklm

        fake_mod, _ = _make_fake_notebooklm()
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            require_notebooklm()  # should not raise


# ---------------------------------------------------------------------------
# create_notebook
# ---------------------------------------------------------------------------


class TestCreateNotebook:
    def _run_create(self, papers_with_paths, artifacts=None, nb_id="nb-42"):
        from mosaic.notebooklm_bridge import create_notebook

        fake_mod, client = _make_fake_notebooklm(nb_id)
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(create_notebook("Test NB", papers_with_paths, artifacts=artifacts))
        return result, client

    def test_returns_notebook_id(self):
        result, _ = self._run_create([])
        assert result.nb_id == "nb-42"

    def test_uploads_local_pdf_when_path_exists(self, tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        paper = Paper(title="A Paper", url="https://example.com/paper")
        _result, client = self._run_create([(paper, pdf)])
        client.sources.add_file.assert_awaited_once_with("nb-42", pdf)
        client.sources.add_url.assert_not_awaited()

    def test_falls_back_to_url_when_no_local_file(self):
        paper = Paper(title="A Paper", url="https://example.com/paper")
        _, client = self._run_create([(paper, None)])
        client.sources.add_url.assert_awaited_once_with("nb-42", "https://example.com/paper")
        client.sources.add_file.assert_not_awaited()

    def test_skips_paper_with_no_path_and_no_url(self):
        paper = Paper(title="A Paper")
        _, client = self._run_create([(paper, None)])
        client.sources.add_file.assert_not_awaited()
        client.sources.add_url.assert_not_awaited()

    def test_source_limit_50(self, tmp_path):
        papers = []
        for i in range(60):
            pdf = tmp_path / f"p{i}.pdf"
            pdf.write_bytes(b"%PDF")
            papers.append((Paper(title=f"Paper {i}"), pdf))
        _, client = self._run_create(papers)
        assert client.sources.add_file.await_count == 50

    def test_podcast_generated_when_flag_set(self):
        paper = Paper(title="A Paper", url="https://example.com/paper")
        _, client = self._run_create([(paper, None)], artifacts={"podcast"})
        client.artifacts.generate_audio.assert_awaited_once_with("nb-42")

    def test_podcast_not_generated_when_flag_false(self):
        paper = Paper(title="A Paper", url="https://example.com/paper")
        _, client = self._run_create([(paper, None)])
        client.artifacts.generate_audio.assert_not_awaited()

    def test_podcast_not_generated_when_no_sources_added(self):
        paper = Paper(title="No URL and no path")
        _, client = self._run_create([(paper, None)], artifacts={"podcast"})
        client.artifacts.generate_audio.assert_not_awaited()

    def test_source_failure_is_non_fatal(self):
        from mosaic.notebooklm_bridge import create_notebook

        paper = Paper(title="A Paper", url="https://example.com/paper")
        fake_mod, client = _make_fake_notebooklm()
        client.sources.add_url = AsyncMock(side_effect=Exception("NLM error"))
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(create_notebook("Test NB", [(paper, None)]))
        assert result.nb_id == "nb-001"  # notebook was still created

    def test_prefers_local_pdf_over_url(self, tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF")
        paper = Paper(title="A Paper", url="https://example.com/paper")
        _, client = self._run_create([(paper, pdf)])
        client.sources.add_file.assert_awaited_once()
        client.sources.add_url.assert_not_awaited()


# ---------------------------------------------------------------------------
# create_notebook_from_dir
# ---------------------------------------------------------------------------


class TestCreateNotebookFromDir:
    def _run_from_dir(self, directory, artifacts=None, nb_id="nb-dir"):
        from mosaic.notebooklm_bridge import create_notebook_from_dir

        fake_mod, client = _make_fake_notebooklm(nb_id)
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(create_notebook_from_dir("Dir NB", directory, artifacts=artifacts))
        return result, client

    def test_raises_when_no_pdfs(self, tmp_path):
        from mosaic.notebooklm_bridge import create_notebook_from_dir

        fake_mod, _ = _make_fake_notebooklm()
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            with pytest.raises(ValueError, match="No PDF files found"):
                _run(create_notebook_from_dir("Empty", tmp_path))

    def test_imports_all_pdfs(self, tmp_path):
        for i in range(3):
            (tmp_path / f"paper{i}.pdf").write_bytes(b"%PDF")
        _, client = self._run_from_dir(tmp_path)
        assert client.sources.add_file.await_count == 3

    def test_source_limit_50(self, tmp_path):
        for i in range(60):
            (tmp_path / f"paper{i:03d}.pdf").write_bytes(b"%PDF")
        _, client = self._run_from_dir(tmp_path)
        assert client.sources.add_file.await_count == 50

    def test_returns_notebook_id(self, tmp_path):
        (tmp_path / "paper.pdf").write_bytes(b"%PDF")
        result, _ = self._run_from_dir(tmp_path)
        assert result.nb_id == "nb-dir"

    def test_podcast_queued_when_flag_set(self, tmp_path):
        (tmp_path / "paper.pdf").write_bytes(b"%PDF")
        _, client = self._run_from_dir(tmp_path, artifacts={"podcast"})
        client.artifacts.generate_audio.assert_awaited_once_with("nb-dir")

    def test_pdf_failure_is_non_fatal(self, tmp_path):
        from mosaic.notebooklm_bridge import create_notebook_from_dir

        (tmp_path / "paper.pdf").write_bytes(b"%PDF")
        fake_mod, client = _make_fake_notebooklm()
        client.sources.add_file = AsyncMock(side_effect=Exception("upload error"))
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(create_notebook_from_dir("Test", tmp_path))
        assert result.nb_id == "nb-001"


# ---------------------------------------------------------------------------
# Issue #30 — outcome reporting, preflight and error messages
# ---------------------------------------------------------------------------


class TestNotebookOutcome:
    def test_artifacts_skipped_when_notebook_empty(self):
        from mosaic.notebooklm_bridge import create_notebook

        fake_mod, client = _make_fake_notebooklm("nb-empty")
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(
                create_notebook("NB", [(Paper(title="no url"), None)], artifacts={"podcast"})
            )
        client.artifacts.generate_audio.assert_not_awaited()
        assert result.sources_added == 0
        assert result.artifacts_skipped == ["podcast"]
        warnings = " ".join(result.warnings())
        assert "empty" in warnings and "podcast" in warnings

    def test_queued_and_failed_artifacts_are_reported(self):
        from mosaic.notebooklm_bridge import create_notebook

        fake_mod, client = _make_fake_notebooklm()
        client.artifacts.generate_report = AsyncMock(side_effect=Exception("quota"))
        paper = Paper(title="P", url="https://example.com/p")
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(
                create_notebook("NB", [(paper, None)], artifacts={"podcast", "briefing", "bogus"})
            )
        assert result.artifacts_queued == ["podcast"]
        assert sorted(result.artifacts_failed) == ["bogus", "briefing"]
        assert result.url == "https://notebooklm.google.com/notebook/nb-001"

    def test_failed_sources_are_counted(self):
        from mosaic.notebooklm_bridge import create_notebook

        fake_mod, client = _make_fake_notebooklm()
        client.sources.add_url = AsyncMock(side_effect=Exception("NLM error"))
        paper = Paper(title="Broken", url="https://example.com/p")
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(create_notebook("NB", [(paper, None)]))
        assert result.sources_failed == ["Broken"]


class TestPreflightAndErrors:
    def test_preflight_not_installed(self):
        from mosaic.notebooklm_bridge import preflight_error

        status = {"installed": False, "authenticated": False}
        with patch("mosaic.notebooklm_bridge.check_notebooklm_status", return_value=status):
            assert "not installed" in preflight_error()

    def test_preflight_not_authenticated(self):
        from mosaic.notebooklm_bridge import preflight_error

        status = {"installed": True, "authenticated": False}
        with patch("mosaic.notebooklm_bridge.check_notebooklm_status", return_value=status):
            assert "notebooklm login" in preflight_error()

    def test_preflight_ok(self):
        from mosaic.notebooklm_bridge import preflight_error

        status = {"installed": True, "authenticated": True}
        with patch("mosaic.notebooklm_bridge.check_notebooklm_status", return_value=status):
            assert preflight_error() is None

    def test_describe_error_maps_auth_failures(self):
        from mosaic.notebooklm_bridge import describe_error

        msg = describe_error(FileNotFoundError("storage_state.json"))
        assert "notebooklm login" in msg
        assert describe_error(RuntimeError("boom")) == "NotebookLM error: boom"


class TestClientCompat:
    def test_context_manager_from_storage_is_not_awaited(self):
        """notebooklm-py >= 0.8: from_storage() returns an async context object."""
        from mosaic.notebooklm_bridge import create_notebook

        fake_mod, client = _make_fake_notebooklm("nb-new")
        fake_mod.NotebookLMClient.from_storage = MagicMock(return_value=client)
        paper = Paper(title="P", url="https://example.com/p")
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            result = _run(create_notebook("NB", [(paper, None)]))
        assert result.nb_id == "nb-new"
        client.__aenter__.assert_awaited_once()
