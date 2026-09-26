"""Tests for mosaic/workflows.py — orchestration shared by the CLI and the web UI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from mosaic.models import Paper
from mosaic.workflows import (
    auto_index,
    bulk_get,
    configure_zotero_key,
    download_papers,
    finalize_search,
    push_to_obsidian,
    push_to_zotero,
)


def _cfg(tmp_path, **extra):
    cfg = {
        "download_dir": str(tmp_path / "pdfs"),
        "filename_pattern": "{year}_{source}_{author}_{title}",
        "unpaywall": {"email": ""},
        "zotero": {"api_key": "", "user_id": 0},
    }
    cfg.update(extra)
    return cfg


# ── download_papers / bulk_get ───────────────────────────────────────────────


class TestDownloadPapers:
    def test_reports_each_outcome(self, tmp_path, tmp_cache):
        ok = Paper(title="ok", doi="10.1/ok")
        fail = Paper(title="fail", doi="10.1/fail")
        nolink = Paper(title="no link")
        seen: list[str] = []

        def fake_dl(paper, *args):
            return str(tmp_path / "ok.pdf") if paper is ok else None

        with patch("mosaic.workflows.dl_paper", side_effect=fake_dl):
            report = download_papers(
                [ok, fail, nolink],
                _cfg(tmp_path),
                tmp_cache,
                on_item=lambda i: seen.append(i.status),
            )

        assert seen == ["ok", "fail", "skip"]
        assert report.pdf_map == {ok.uid: str(tmp_path / "ok.pdf")}
        assert (report.count("ok"), report.count("fail"), report.count("skip")) == (1, 1, 1)

    def test_skip_without_link_can_be_disabled(self, tmp_path, tmp_cache):
        with patch("mosaic.workflows.dl_paper", return_value=None) as dl:
            report = download_papers(
                [Paper(title="x")], _cfg(tmp_path), tmp_cache, skip_without_link=False
            )
        dl.assert_called_once()
        assert report.items[0].status == "fail"


class TestBulkGet:
    def test_uses_cached_metadata(self, tmp_path, tmp_cache):
        cached = Paper(title="Cached title", doi="10.1/a", year=2020, source="arXiv")
        tmp_cache.save(cached)
        with patch("mosaic.workflows.dl_paper", return_value=None) as dl:
            papers, report = bulk_get(["10.1/A", "10.1/b"], _cfg(tmp_path), tmp_cache)
        # The downloader received the cached record (title, year, …), not a bare stub
        assert dl.call_args_list[0].args[0].title == "Cached title"
        assert [p.title for p in papers] == ["Cached title", "10.1/b"]
        assert report.count("fail") == 2


# ── finalize_search ──────────────────────────────────────────────────────────


class TestFinalizeSearch:
    def test_prefer_cache_applies_before_pdf_filter(self, tmp_path, tmp_cache):
        rich = Paper(
            title="T",
            doi="10.1/x",
            abstract="A rich abstract",
            authors=["A"],
            year=2020,
            pdf_url="https://example.org/x.pdf",
            source="s",
        )
        tmp_cache.save(rich)
        fresh = Paper(title="T", doi="10.1/x", source="s")
        with patch.object(tmp_cache, "rich_uids", return_value={rich.uid}):
            out = finalize_search(
                [fresh], _cfg(tmp_path), tmp_cache, query="T", pdf_only=True, prefer_cache=True
            )
        assert [p.pdf_url for p in out] == ["https://example.org/x.pdf"]

    def test_saves_and_logs_history(self, tmp_path, tmp_cache):
        p = Paper(title="Logged", doi="10.1/log", source="s")
        finalize_search(
            [p],
            _cfg(tmp_path),
            tmp_cache,
            query="logged",
            history={"filters": {"year": "2020"}, "sources": ["arXiv"]},
        )
        assert tmp_cache.get_by_uid(p.uid) is not None
        entry = tmp_cache.list_searches()[0]
        assert entry["query"] == "logged" and entry["result_count"] == 1
        assert json.loads(entry["filters_json"]) == {"year": "2020"}

    def test_save_false_leaves_cache_untouched(self, tmp_path, tmp_cache):
        p = Paper(title="Not saved", doi="10.1/ns", source="s")
        finalize_search([p], _cfg(tmp_path), tmp_cache, query="q", save=False)
        assert tmp_cache.get_by_uid(p.uid) is None


# ── auto_index ───────────────────────────────────────────────────────────────


class TestAutoIndex:
    def test_disabled_is_noop(self, tmp_path, tmp_cache):
        with patch("mosaic.rag.index_papers") as idx:
            assert auto_index([Paper(title="x")], _cfg(tmp_path), tmp_cache) is None
        idx.assert_not_called()

    def test_failure_is_reported_not_swallowed(self, tmp_path, tmp_cache):
        cfg = _cfg(tmp_path, rag={"auto_index": True})
        with patch("mosaic.rag.index_papers", side_effect=ValueError("no embedding model")):
            msg = auto_index([Paper(title="x")], cfg, tmp_cache)
        assert msg == "Auto-index failed: no embedding model"


# ── Zotero ───────────────────────────────────────────────────────────────────


class TestZotero:
    def test_user_id_discovered_when_missing(self, tmp_path):
        cfg = _cfg(tmp_path, zotero={"api_key": "KEY", "user_id": 0})
        client = MagicMock()
        client.discover_user_id.return_value = 4242
        client.add_papers.return_value = ["K1"]
        with patch("mosaic.zotero.ZoteroClient", return_value=client):
            result = push_to_zotero([Paper(title="p", doi="10.1/p")], cfg)
        assert result["ok"] is True
        client.discover_user_id.assert_called_once()
        assert cfg["zotero"]["user_id"] == 4242

    def test_write_errors_become_results(self, tmp_path):
        client = MagicMock()
        client.add_papers.side_effect = RuntimeError("local API rejected the write")
        with patch("mosaic.zotero.ZoteroClient", return_value=client):
            result = push_to_zotero([Paper(title="p", doi="10.1/p")], _cfg(tmp_path))
        assert result["ok"] is False
        assert "local API rejected the write" in result["msg"]

    def test_configure_zotero_key(self, tmp_path):
        cfg = _cfg(tmp_path)
        with patch("mosaic.zotero.ZoteroClient") as cls:
            cls.return_value.discover_user_id.return_value = 7
            assert configure_zotero_key(cfg, "NEWKEY") is None
        assert cfg["zotero"] == {"api_key": "NEWKEY", "user_id": 7}

    def test_configure_zotero_key_discovery_failure(self, tmp_path):
        cfg = _cfg(tmp_path, zotero={"api_key": "OLD", "user_id": 3})
        with patch("mosaic.zotero.ZoteroClient") as cls:
            cls.return_value.discover_user_id.side_effect = RuntimeError("offline")
            warning = configure_zotero_key(cfg, "NEWKEY")
        assert "offline" in warning
        # a new key never keeps the previous key's user ID
        assert cfg["zotero"] == {"api_key": "NEWKEY", "user_id": 0}


# ── Obsidian ─────────────────────────────────────────────────────────────────


class TestObsidian:
    def test_missing_vault(self, tmp_path):
        assert push_to_obsidian([], _cfg(tmp_path, obsidian={}))["ok"] is False

    def test_write_error_is_reported(self, tmp_path):
        cfg = _cfg(tmp_path, obsidian={"vault_path": str(tmp_path / "vault")})
        with patch(
            "mosaic.obsidian.ObsidianVault.export_papers", side_effect=PermissionError("ro")
        ):
            result = push_to_obsidian([Paper(title="p")], cfg)
        assert result["ok"] is False and "ro" in result["msg"]
