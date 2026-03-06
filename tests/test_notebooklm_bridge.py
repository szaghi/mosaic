"""Tests for the NotebookLM bridge module."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
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

    NotebookLMClient = MagicMock()
    NotebookLMClient.from_storage = AsyncMock(return_value=client)

    mod = ModuleType("notebooklm")
    mod.NotebookLMClient = NotebookLMClient  # type: ignore[attr-defined]

    return mod, client


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _require_notebooklm
# ---------------------------------------------------------------------------

class TestRequireNotebooklm:
    def test_raises_when_not_installed(self):
        from mosaic.notebooklm_bridge import _require_notebooklm
        with patch.dict(sys.modules, {"notebooklm": None}):
            with pytest.raises(ImportError, match="mosaic-search\\[notebooklm\\]"):
                _require_notebooklm()

    def test_passes_when_installed(self):
        from mosaic.notebooklm_bridge import _require_notebooklm
        fake_mod, _ = _make_fake_notebooklm()
        with patch.dict(sys.modules, {"notebooklm": fake_mod}):
            _require_notebooklm()  # should not raise


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
        assert result == "nb-42"

    def test_uploads_local_pdf_when_path_exists(self, tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        paper = Paper(title="A Paper", url="https://example.com/paper")
        result, client = self._run_create([(paper, pdf)])
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
        assert result == "nb-001"  # notebook was still created

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
        assert result == "nb-dir"

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
        assert result == "nb-001"
