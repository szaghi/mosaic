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
    def test_raises_dependency_error_when_not_installed(self):
        """A typed error, never SystemExit: it must not escape ``except Exception`` (#30)."""
        from mosaic.errors import DependencyError, MosaicError

        with patch.dict("sys.modules", {"playwright": None}):
            with pytest.raises(DependencyError, match="mosaic-search\\[browser\\]") as exc_info:
                _require_playwright()
        assert isinstance(exc_info.value, MosaicError)


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


class TestBrowserDownloadContentCheck:
    """Issue #42: a 200 HTML challenge page from the browser must not be saved."""

    def _download(self, tmp_path, body: bytes, nav_body: bytes | None = None) -> bool:
        """Run browser_download; *body* is the request-API response, *nav_body*
        what navigating the page to the PDF downloads (None: no download)."""
        import contextlib
        import sys

        import mosaic.auth as auth_mod

        response = AsyncMock()
        response.ok = True
        response.headers = {"content-type": "text/html"}
        response.body = AsyncMock(return_value=body)

        mock_page = AsyncMock()
        mock_page.url = "https://sciencedirect.com/article/123"
        mock_page.goto = AsyncMock()

        @contextlib.asynccontextmanager
        async def expect_download(timeout=None):
            info = MagicMock()
            if nav_body is None:
                fut = asyncio.get_running_loop().create_future()
                fut.set_exception(TimeoutError("no download"))
            else:
                saved = tmp_path / "nav-download.bin"
                saved.write_bytes(nav_body)
                download = MagicMock()
                download.path = AsyncMock(return_value=str(saved))
                fut = asyncio.get_running_loop().create_future()
                fut.set_result(download)
            info.value = fut
            yield info

        mock_page.expect_download = expect_download

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.request.get = AsyncMock(return_value=response)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw_cm = AsyncMock()
        mock_pw_cm.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_pw_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pw_module = MagicMock()
        mock_pw_module.async_playwright = MagicMock(return_value=mock_pw_cm)

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _make_session(tmp_path, "elsevier", "https://sciencedirect.com/user/login")
            with (
                patch("mosaic.auth._require_playwright", return_value=None),
                patch("mosaic.auth._launch_browser", AsyncMock(return_value=mock_browser)),
                patch("mosaic.auth._find_pdf_url", AsyncMock(return_value="https://x/p.pdf")),
                patch.dict(sys.modules, {"playwright.async_api": mock_pw_module}),
            ):
                return asyncio.run(
                    browser_download(
                        "https://sciencedirect.com/article/123",
                        str(tmp_path / "out.pdf"),
                        "elsevier",
                    )
                )
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_html_body_rejected(self, tmp_path):
        assert self._download(tmp_path, b"<html>Client Challenge</html>") is False
        assert not (tmp_path / "out.pdf").exists()

    def test_pdf_body_saved(self, tmp_path):
        assert self._download(tmp_path, b"%PDF-1.7 body") is True
        assert (tmp_path / "out.pdf").read_bytes() == b"%PDF-1.7 body"
        assert not (tmp_path / "out.pdf.part").exists()

    def test_js_wall_falls_back_to_page_navigation_download(self, tmp_path):
        """Springer: the request API gets an HTML challenge, a real navigation gets the PDF."""
        html = b"<html>Client Challenge</html>"
        assert self._download(tmp_path, html, nav_body=b"%PDF-1.5 real") is True
        assert (tmp_path / "out.pdf").read_bytes() == b"%PDF-1.5 real"

    def test_navigation_download_that_is_not_pdf_rejected(self, tmp_path):
        html = b"<html>Client Challenge</html>"
        assert self._download(tmp_path, html, nav_body=b"<html>still a wall</html>") is False
        assert not (tmp_path / "out.pdf").exists()
