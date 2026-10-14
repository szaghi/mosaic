"""Tests for the PDF downloader."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mosaic.downloader import _fetch, download
from mosaic.errors import DownloadError
from mosaic.models import Paper

_PDF = b"%PDF-1.7\n" + b"x" * 4000
_HTML = b"<!DOCTYPE html><html><title>Client Challenge</title></html>"


@contextmanager
def _stream(chunks, content_type="application/pdf"):
    """Stand-in for ``httpx.stream`` yielding *chunks* with a 200 status."""
    resp = MagicMock()
    resp.headers = {"content-type": content_type}
    resp.iter_bytes = MagicMock(return_value=iter(chunks))
    yield resp


def _paper(doi="10.1/test", pdf_url=None):
    return Paper(
        title="Test Paper",
        authors=["Smith"],
        year=2020,
        doi=doi,
        pdf_url=pdf_url,
        source="test",
    )


class TestDownload:
    def test_skips_if_already_cached_and_file_exists(self, tmp_path, tmp_cache):
        dest = tmp_path / "paper.pdf"
        dest.write_bytes(_PDF)
        p = _paper()
        tmp_cache.set_download(p.uid, str(dest), "ok")
        with patch("mosaic.downloader._fetch") as mock_fetch:
            result = download(p, str(tmp_path), tmp_cache)
        mock_fetch.assert_not_called()
        assert result == str(dest)

    def test_downloads_from_pdf_url(self, tmp_path, tmp_cache):
        p = _paper(pdf_url="https://example.com/paper.pdf")
        with patch("mosaic.downloader._fetch") as mock_fetch:
            result = download(p, str(tmp_path), tmp_cache)
        mock_fetch.assert_called_once()
        assert "https://example.com/paper.pdf" in mock_fetch.call_args.args
        assert result is not None

    def test_falls_back_to_unpaywall_when_no_pdf_url(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        with (
            patch("mosaic.sources.unpaywall.resolve", return_value="https://repo.org/paper.pdf"),
            patch("mosaic.downloader._fetch"),
        ):
            result = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        assert result is not None

    def test_returns_none_when_no_pdf_and_no_doi(self, tmp_path, tmp_cache):
        p = Paper(title="T", authors=[], doi=None, pdf_url=None)
        result = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        assert result is None

    def test_returns_none_and_records_error_on_fetch_failure(self, tmp_path, tmp_cache):
        p = _paper(pdf_url="https://example.com/paper.pdf")
        with patch("mosaic.downloader._fetch", side_effect=Exception("connection refused")):
            result = download(p, str(tmp_path), tmp_cache)
        assert result is None
        rec = tmp_cache.get_download(p.uid)
        assert rec is not None
        assert "error" in rec["status"]

    def test_cache_recorded_as_ok_after_success(self, tmp_path, tmp_cache):
        p = _paper(pdf_url="https://example.com/paper.pdf")
        with patch("mosaic.downloader._fetch"):
            download(p, str(tmp_path), tmp_cache)
        rec = tmp_cache.get_download(p.uid)
        assert rec["status"] == "ok"

    def test_falls_back_to_browser_when_steps_1_and_2_fail(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        p.url = "https://sciencedirect.com/article/pii/S123"
        with (
            patch("mosaic.sources.unpaywall.resolve", return_value=None),
            patch("mosaic.auth.find_session_for_url", return_value="elsevier"),
            patch("mosaic.auth.browser_download", new=AsyncMock(return_value=True)),
        ):
            result = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        assert result is not None

    def test_skips_browser_when_no_session_matches(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        p.url = "https://nature.com/articles/123"
        with (
            patch("mosaic.sources.unpaywall.resolve", return_value=None),
            patch("mosaic.auth.find_session_for_url", return_value=None),
            patch("mosaic.auth.list_sessions", return_value=[]),
            patch("mosaic.auth.browser_download") as mock_bd,
        ):
            download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        mock_bd.assert_not_called()

    def test_browser_result_cached_as_ok(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        p.url = "https://sciencedirect.com/article/pii/S123"
        with (
            patch("mosaic.sources.unpaywall.resolve", return_value=None),
            patch("mosaic.auth.find_session_for_url", return_value="elsevier"),
            patch("mosaic.auth.browser_download", AsyncMock(return_value=True)),
        ):
            download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        rec = tmp_cache.get_download(p.uid)
        assert rec["status"] == "ok"

    def test_all_steps_fail_returns_none(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        with (
            patch("mosaic.sources.unpaywall.resolve", return_value=None),
            patch("mosaic.auth.find_session_for_url", return_value=None),
            patch("mosaic.auth.list_sessions", return_value=[]),
            patch("mosaic.downloader._resolve_redirect", side_effect=lambda u: u),
        ):
            result = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        assert result is None


class TestFetchRejectsNonPdf:
    """Issue #42: 200-status HTML pages must never be saved as PDFs."""

    def test_html_body_raises_and_leaves_no_file(self, tmp_path):
        dest = tmp_path / "paper.pdf"
        with (
            patch("mosaic.downloader.httpx.stream", return_value=_stream([_HTML], "text/html")),
            pytest.raises(DownloadError, match="text/html"),
        ):
            _fetch("https://example.com/paper.pdf", str(dest))
        assert list(tmp_path.iterdir()) == []

    def test_pdf_body_in_tiny_chunks_is_accepted(self, tmp_path):
        dest = tmp_path / "paper.pdf"
        chunks = [_PDF[i : i + 3] for i in range(0, len(_PDF), 3)]
        with patch("mosaic.downloader.httpx.stream", return_value=_stream(chunks)):
            _fetch("https://example.com/paper.pdf", str(dest))
        assert dest.read_bytes() == _PDF
        assert list(tmp_path.iterdir()) == [dest]

    def test_short_pdf_body_is_accepted(self, tmp_path):
        dest = tmp_path / "paper.pdf"
        with patch("mosaic.downloader.httpx.stream", return_value=_stream([b"%PDF-1.4 tiny"])):
            _fetch("https://example.com/paper.pdf", str(dest))
        assert dest.read_bytes() == b"%PDF-1.4 tiny"

    def test_empty_body_raises(self, tmp_path):
        dest = tmp_path / "paper.pdf"
        with (
            patch("mosaic.downloader.httpx.stream", return_value=_stream([])),
            pytest.raises(DownloadError),
        ):
            _fetch("https://example.com/paper.pdf", str(dest))
        assert not dest.exists()

    def test_transport_error_mid_stream_leaves_no_partial_file(self, tmp_path):
        dest = tmp_path / "paper.pdf"

        def _chunks():
            yield _PDF[:2000]
            raise OSError("connection reset")

        with (
            patch("mosaic.downloader.httpx.stream", return_value=_stream(_chunks())),
            pytest.raises(OSError),
        ):
            _fetch("https://example.com/paper.pdf", str(dest))
        assert list(tmp_path.iterdir()) == []


class TestDownloadNonPdf:
    def test_html_response_is_not_cached_as_ok(self, tmp_path, tmp_cache):
        p = _paper(pdf_url="https://arxiv.org/abs/1706.03762")
        with (
            patch("mosaic.downloader.httpx.stream", return_value=_stream([_HTML], "text/html")),
            patch("mosaic.downloader._resolve_redirect", side_effect=lambda u: u),
            patch("mosaic.auth.find_session_for_url", return_value=None),
            patch("mosaic.auth.list_sessions", return_value=[]),
        ):
            result = download(p, str(tmp_path), tmp_cache)
        assert result is None
        assert not any(tmp_path.glob("*.pdf*"))
        assert tmp_cache.get_download(p.uid)["status"] == "error: not a pdf (text/html)"

    def test_html_from_pdf_url_falls_through_to_unpaywall(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url="https://publisher.com/landing")
        streams = iter([_stream([_HTML], "text/html"), _stream([_PDF])])
        with (
            patch("mosaic.downloader.httpx.stream", side_effect=lambda *a, **k: next(streams)),
            patch("mosaic.sources.unpaywall.resolve", return_value="https://repo.org/p.pdf"),
        ):
            result = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        assert result is not None
        assert tmp_cache.get_download(p.uid)["status"] == "ok"

    def test_cached_html_file_is_retried(self, tmp_path, tmp_cache):
        """An "ok" record written by an older version for an HTML page heals itself."""
        p = _paper(pdf_url="https://example.com/paper.pdf")
        stale = tmp_path / "stale.pdf"
        stale.write_bytes(_HTML)
        tmp_cache.set_download(p.uid, str(stale), "ok")
        with patch("mosaic.downloader._fetch") as mock_fetch:
            result = download(p, str(tmp_path), tmp_cache)
        mock_fetch.assert_called_once()
        assert result is not None and result != str(stale)
