"""Tests for mosaic.auth — session management and browser download."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mosaic.auth import (
    _absolutise,
    _find_pdf_url,
    _load_meta,
    _meta_path,
    _require_playwright,
    _save_meta,
    browser_download,
    delete_session,
    find_session_for_url,
    list_sessions,
    session_path,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_session(tmp_path: Path, name: str, login_url: str) -> Path:
    """Create a fake session file + metadata in tmp_path."""
    import mosaic.auth as auth_mod

    orig = auth_mod._SESSIONS_DIR
    auth_mod._SESSIONS_DIR = tmp_path
    try:
        _save_meta(name, login_url)
        sp = session_path(name)
        sp.write_text('{"cookies": [], "origins": []}')
        return sp
    finally:
        auth_mod._SESSIONS_DIR = orig


# ── session path helpers ──────────────────────────────────────────────────────


class TestSessionPath:
    def test_returns_json_path(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            assert session_path("elsevier") == tmp_path / "elsevier.json"
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_meta_path_suffix(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            assert _meta_path("elsevier") == tmp_path / "elsevier.meta.json"
        finally:
            auth_mod._SESSIONS_DIR = orig


# ── metadata save / load ──────────────────────────────────────────────────────


class TestMeta:
    def test_save_and_load_roundtrip(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _save_meta("springer", "https://link.springer.com/login")
            meta = _load_meta("springer")
            assert meta["login_url"] == "https://link.springer.com/login"
            assert meta["domain"] == "link.springer.com"
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_load_missing_returns_empty(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            assert _load_meta("nonexistent") == {}
        finally:
            auth_mod._SESSIONS_DIR = orig


# ── list_sessions ─────────────────────────────────────────────────────────────


class TestListSessions:
    def test_empty_when_no_dir(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path / "nonexistent"
        try:
            assert list_sessions() == []
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_lists_saved_sessions(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            _make_session(tmp_path, "springer", "https://link.springer.com/login")
            sessions = list_sessions()
            names = [s["name"] for s in sessions]
            assert "elsevier" in names
            assert "springer" in names
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_includes_domain(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            sessions = list_sessions()
            assert sessions[0]["domain"] == "sciencedirect.com"
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_excludes_meta_files(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            sessions = list_sessions()
            assert all(not s["name"].endswith(".meta") for s in sessions)
        finally:
            auth_mod._SESSIONS_DIR = orig


# ── delete_session ────────────────────────────────────────────────────────────


class TestDeleteSession:
    def test_returns_true_when_exists(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            assert delete_session("elsevier") is True
            assert not session_path("elsevier").exists()
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_removes_meta_file(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            delete_session("elsevier")
            assert not _meta_path("elsevier").exists()
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_returns_false_when_not_exists(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            assert delete_session("nonexistent") is False
        finally:
            auth_mod._SESSIONS_DIR = orig


# ── find_session_for_url ──────────────────────────────────────────────────────


class TestFindSessionForUrl:
    def test_matches_by_domain(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            result = find_session_for_url("https://sciencedirect.com/article/pii/S123")
            assert result == "elsevier"
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_returns_none_when_no_match(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            result = find_session_for_url("https://nature.com/articles/123")
            assert result is None
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_returns_none_for_empty_url(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            assert find_session_for_url("") is None
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_returns_none_when_no_sessions_dir(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path / "nonexistent"
        try:
            assert find_session_for_url("https://sciencedirect.com/article") is None
        finally:
            auth_mod._SESSIONS_DIR = orig


# ── _absolutise ───────────────────────────────────────────────────────────────


class TestAbsolutise:
    def test_absolute_url_unchanged(self):
        assert (
            _absolutise("https://example.com/file.pdf", "https://other.com")
            == "https://example.com/file.pdf"
        )

    def test_root_relative(self):
        result = _absolutise("/download/paper.pdf", "https://example.com/article/123")
        assert result == "https://example.com/download/paper.pdf"

    def test_relative_path(self):
        result = _absolutise("paper.pdf", "https://example.com/article/")
        assert result == "https://example.com/paper.pdf"


# ── _require_playwright ───────────────────────────────────────────────────────


class TestRequirePlaywright:
    def test_raises_system_exit_when_not_installed(self):
        with patch.dict("sys.modules", {"playwright": None}):
            with pytest.raises((SystemExit, ImportError)):
                _require_playwright()


# ── _find_pdf_url ─────────────────────────────────────────────────────────────


class TestFindPdfUrl:
    def _run(self, coro):
        return asyncio.run(coro)

    def _mock_page(self, selector_result=None, links=None):
        page = AsyncMock()
        page.url = "https://example.com/article/123"

        async def query_selector(sel):
            if selector_result and "pdf" in sel.lower():
                el = AsyncMock()
                el.get_attribute = AsyncMock(return_value=selector_result)
                return el
            return None

        async def query_selector_all(sel):
            return links or []

        page.query_selector = query_selector
        page.query_selector_all = query_selector_all
        return page

    def test_finds_link_via_css_selector(self):
        page = self._mock_page(selector_result="https://example.com/paper.pdf")
        result = self._run(_find_pdf_url(page))
        assert result == "https://example.com/paper.pdf"

    def test_finds_link_via_text(self):
        page = self._mock_page(selector_result=None)

        link = AsyncMock()
        link.inner_text = AsyncMock(return_value="Download PDF")
        link.get_attribute = AsyncMock(return_value="/download/paper.pdf")

        page.query_selector_all = AsyncMock(return_value=[link])
        result = self._run(_find_pdf_url(page))
        assert result is not None
        assert "paper.pdf" in result

    def test_returns_none_when_no_pdf_link(self):
        page = self._mock_page(selector_result=None, links=[])
        result = self._run(_find_pdf_url(page))
        assert result is None


# ── browser_download ──────────────────────────────────────────────────────────


class TestBrowserDownload:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_returns_false_when_session_missing(self, tmp_path):
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            result = self._run(
                browser_download(
                    "https://example.com/article", str(tmp_path / "out.pdf"), "elsevier"
                )
            )
            assert result is False
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_returns_false_when_no_pdf_link_found(self, tmp_path):
        import sys

        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")

            mock_page = AsyncMock()
            mock_page.url = "https://sciencedirect.com/article/123"
            mock_page.query_selector = AsyncMock(return_value=None)
            mock_page.query_selector_all = AsyncMock(return_value=[])
            mock_page.goto = AsyncMock()

            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_context.request = AsyncMock()

            mock_browser = AsyncMock()
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_browser.close = AsyncMock()

            mock_pw_cm = AsyncMock()
            mock_pw_cm.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

            mock_pw_module = MagicMock()
            mock_pw_module.async_playwright = MagicMock(return_value=mock_pw_cm)

            with (
                patch("mosaic.auth._require_playwright", return_value=None),
                patch("mosaic.auth._launch_browser", AsyncMock(return_value=mock_browser)),
                patch.dict(sys.modules, {"playwright.async_api": mock_pw_module}),
            ):
                result = self._run(
                    browser_download(
                        "https://sciencedirect.com/article/123",
                        str(tmp_path / "out.pdf"),
                        "elsevier",
                    )
                )
            assert result is False
        finally:
            auth_mod._SESSIONS_DIR = orig
