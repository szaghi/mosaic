"""Download robustness: PDF validation, atomic writes, filename collisions."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mosaic.auth import _save_meta, browser_download, session_path
from mosaic.downloader import NotAPDFError, _fetch, download, looks_like_pdf
from mosaic.models import Paper

_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"
_HTML = b"<!DOCTYPE html><html><body>Please sign in</body></html>"


def _stream_cm(chunks: list[bytes], *, fail_after: int | None = None, status_error=False):
    """Mock for ``httpx.stream(...)`` used as a context manager."""
    resp = MagicMock()
    resp.headers = {"content-type": "application/pdf"}
    if status_error:
        req = httpx.Request("GET", "https://x.org/p.pdf")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=req, response=httpx.Response(403, request=req)
        )

    def _iter(_size):
        for i, c in enumerate(chunks):
            if fail_after is not None and i >= fail_after:
                raise httpx.ReadError("connection reset")
            yield c

    resp.iter_bytes.side_effect = _iter
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


class TestLooksLikePdf:
    def test_pdf_header(self):
        assert looks_like_pdf(_PDF)

    def test_header_after_small_preamble(self):
        assert looks_like_pdf(b"\n\n  " + _PDF)

    def test_html(self):
        assert not looks_like_pdf(_HTML)

    def test_empty(self):
        assert not looks_like_pdf(b"")


class TestFetch:
    def test_writes_pdf_and_no_part_file(self, tmp_path):
        dest = tmp_path / "p.pdf"
        with patch("mosaic.downloader.httpx.stream", return_value=_stream_cm([_PDF[:3], _PDF[3:]])):
            _fetch("https://x.org/p.pdf", str(dest))
        assert dest.read_bytes() == _PDF
        assert not (tmp_path / "p.pdf.part").exists()

    def test_rejects_html(self, tmp_path):
        dest = tmp_path / "p.pdf"
        with patch("mosaic.downloader.httpx.stream", return_value=_stream_cm([_HTML])):
            with pytest.raises(NotAPDFError):
                _fetch("https://x.org/p.pdf", str(dest))
        assert not dest.exists()
        assert not (tmp_path / "p.pdf.part").exists()

    def test_interrupted_stream_leaves_no_partial_file(self, tmp_path):
        dest = tmp_path / "p.pdf"
        cm = _stream_cm([_PDF[:10], _PDF[10:]], fail_after=1)
        with patch("mosaic.downloader.httpx.stream", return_value=cm):
            with pytest.raises(httpx.ReadError):
                _fetch("https://x.org/p.pdf", str(dest))
        assert not dest.exists()
        assert not (tmp_path / "p.pdf.part").exists()

    def test_failure_keeps_existing_good_file(self, tmp_path):
        dest = tmp_path / "p.pdf"
        dest.write_bytes(b"%PDF-1.4 previous good copy")
        with patch("mosaic.downloader.httpx.stream", return_value=_stream_cm([_HTML])):
            with pytest.raises(NotAPDFError):
                _fetch("https://x.org/p.pdf", str(dest))
        assert dest.read_bytes() == b"%PDF-1.4 previous good copy"

    def test_http_error_propagates(self, tmp_path):
        dest = tmp_path / "p.pdf"
        with patch(
            "mosaic.downloader.httpx.stream", return_value=_stream_cm([], status_error=True)
        ):
            with pytest.raises(httpx.HTTPStatusError):
                _fetch("https://x.org/p.pdf", str(dest))
        assert not dest.exists()


class TestDownloadValidation:
    def test_html_from_pdf_url_falls_back_to_unpaywall(self, tmp_path, tmp_cache):
        p = Paper(title="T", authors=["A B"], year=2020, doi="10.1/x", pdf_url="https://pub/x")
        calls = []

        def fake_stream(method, url, **kw):
            calls.append(url)
            return _stream_cm([_HTML] if url == "https://pub/x" else [_PDF])

        with (
            patch("mosaic.downloader.httpx.stream", side_effect=fake_stream),
            patch("mosaic.sources.unpaywall.resolve", return_value="https://repo/x.pdf"),
        ):
            path = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@x.org")
        assert calls == ["https://pub/x", "https://repo/x.pdf"]
        assert path is not None and Path(path).read_bytes() == _PDF
        assert tmp_cache.get_download(p.uid)["status"] == "ok"

    def test_html_everywhere_is_not_recorded_as_ok(self, tmp_path, tmp_cache):
        p = Paper(title="T", doi=None, pdf_url="https://pub/x")
        with patch("mosaic.downloader.httpx.stream", return_value=_stream_cm([_HTML])):
            assert download(p, str(tmp_path), tmp_cache) is None
        assert tmp_cache.get_download(p.uid)["status"].startswith("error")

    def test_missing_playwright_does_not_crash(self, tmp_path, tmp_cache):
        p = Paper(title="T", doi="10.1/x", url="https://sciencedirect.com/a")
        with (
            patch("mosaic.downloader._resolve_redirect", side_effect=lambda u: u),
            patch("mosaic.auth.find_session_for_url", return_value="elsevier"),
            patch(
                "mosaic.auth.browser_download",
                new=AsyncMock(side_effect=ImportError("Playwright is not installed.")),
            ),
        ):
            assert download(p, str(tmp_path), tmp_cache) is None


class TestFilenameCollisions:
    def _pair(self):
        title = "A survey of deep learning methods for medical image segmentation tasks"
        a = Paper(title=title, authors=["Wei Zhang"], year=2020, doi="10.1/a", source="arXiv")
        b = Paper(title=title, authors=["Wei Li"], year=2020, doi="10.1/b", source="arXiv")
        assert a.safe_filename() == b.safe_filename()  # the collision being fixed
        return a, b

    def test_second_paper_gets_suffixed_name(self, tmp_path, tmp_cache):
        a, b = self._pair()
        with patch("mosaic.downloader._fetch", side_effect=lambda u, d: Path(d).write_bytes(_PDF)):
            pa = download(Paper(**{**a.to_dict(), "pdf_url": "u"}), str(tmp_path), tmp_cache)
            pb = download(Paper(**{**b.to_dict(), "pdf_url": "u"}), str(tmp_path), tmp_cache)
        assert pa != pb
        assert Path(pa).name == a.safe_filename()
        assert Path(pb).stem.startswith(Path(pa).stem + "_")
        assert Path(pa).exists() and Path(pb).exists()

    def test_redownload_of_same_paper_keeps_its_name(self, tmp_path, tmp_cache):
        a, _ = self._pair()
        a.pdf_url = "u"
        dest = tmp_path / a.safe_filename()
        tmp_cache.set_download(a.uid, str(dest), "ok")  # recorded, but file was deleted
        with patch("mosaic.downloader._fetch", side_effect=lambda u, d: Path(d).write_bytes(_PDF)):
            path = download(a, str(tmp_path), tmp_cache)
        assert path == str(dest)

    def test_non_colliding_name_unchanged(self, tmp_path, tmp_cache):
        p = Paper(title="Unique", authors=["Ann Lee"], year=2021, doi="10.1/u", pdf_url="u")
        with patch("mosaic.downloader._fetch", side_effect=lambda u, d: Path(d).write_bytes(_PDF)):
            path = download(p, str(tmp_path), tmp_cache)
        assert Path(path).name == p.safe_filename()


class TestBrowserDownloadValidation:
    def _download(self, tmp_path, body: bytes, dest: Path) -> bool:
        import mosaic.auth as auth_mod

        orig = auth_mod._SESSIONS_DIR
        auth_mod._SESSIONS_DIR = tmp_path
        try:
            _save_meta("elsevier", "https://sciencedirect.com/user/login")
            session_path("elsevier").write_text('{"cookies": [], "origins": []}')

            el = AsyncMock()
            el.get_attribute = AsyncMock(return_value="/pdf/paper.pdf")
            page = AsyncMock()
            page.url = "https://sciencedirect.com/article/123"
            page.query_selector = AsyncMock(return_value=el)

            response = MagicMock()
            response.ok = True
            response.body = AsyncMock(return_value=body)
            context = AsyncMock()
            context.new_page = AsyncMock(return_value=page)
            context.request = MagicMock()
            context.request.get = AsyncMock(return_value=response)

            browser = AsyncMock()
            browser.new_context = AsyncMock(return_value=context)

            pw_cm = AsyncMock()
            pw_cm.__aenter__ = AsyncMock(return_value=MagicMock())
            pw_cm.__aexit__ = AsyncMock(return_value=False)
            pw_module = MagicMock()
            pw_module.async_playwright = MagicMock(return_value=pw_cm)

            with (
                patch("mosaic.auth._require_playwright", return_value=None),
                patch("mosaic.auth._launch_browser", AsyncMock(return_value=browser)),
                patch.dict(sys.modules, {"playwright.async_api": pw_module}),
            ):
                return asyncio.run(
                    browser_download("https://sciencedirect.com/article/123", str(dest), "elsevier")
                )
        finally:
            auth_mod._SESSIONS_DIR = orig

    def test_saves_real_pdf(self, tmp_path):
        dest = tmp_path / "out" / "paper.pdf"
        assert self._download(tmp_path, _PDF, dest) is True
        assert dest.read_bytes() == _PDF
        assert not (tmp_path / "out" / "paper.pdf.part").exists()

    def test_rejects_html_login_page(self, tmp_path):
        dest = tmp_path / "paper.pdf"
        assert self._download(tmp_path, _HTML, dest) is False
        assert not dest.exists()

    def test_html_page_does_not_clobber_existing_file(self, tmp_path):
        dest = tmp_path / "paper.pdf"
        dest.write_bytes(b"%PDF-1.4 good")
        assert self._download(tmp_path, _HTML, dest) is False
        assert dest.read_bytes() == b"%PDF-1.4 good"
