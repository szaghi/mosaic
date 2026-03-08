"""Tests for the PDF downloader."""
from unittest.mock import patch, MagicMock
from mosaic.models import Paper
from mosaic.downloader import download
from mosaic.db import Cache


def _paper(doi="10.1/test", pdf_url=None):
    return Paper(
        title="Test Paper", authors=["Smith"], year=2020,
        doi=doi, pdf_url=pdf_url, source="test",
    )


class TestDownload:
    def test_skips_if_already_cached_and_file_exists(self, tmp_path, tmp_cache):
        dest = tmp_path / "paper.pdf"
        dest.write_bytes(b"pdf content")
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
        with patch("mosaic.sources.unpaywall.resolve", return_value="https://repo.org/paper.pdf"), \
             patch("mosaic.downloader._fetch"):
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
        with patch("mosaic.sources.unpaywall.resolve", return_value=None), \
             patch("mosaic.auth.find_session_for_url", return_value="elsevier"), \
             patch("mosaic.auth.browser_download", return_value=True) as mock_bd, \
             patch("asyncio.run", side_effect=lambda coro: True):
            result = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        assert result is not None

    def test_skips_browser_when_no_session_matches(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        p.url = "https://nature.com/articles/123"
        with patch("mosaic.sources.unpaywall.resolve", return_value=None), \
             patch("mosaic.auth.find_session_for_url", return_value=None), \
             patch("mosaic.auth.browser_download") as mock_bd:
            download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        mock_bd.assert_not_called()

    def test_browser_result_cached_as_ok(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        p.url = "https://sciencedirect.com/article/pii/S123"
        with patch("mosaic.sources.unpaywall.resolve", return_value=None), \
             patch("mosaic.auth.find_session_for_url", return_value="elsevier"), \
             patch("asyncio.run", return_value=True):
            download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        rec = tmp_cache.get_download(p.uid)
        assert rec["status"] == "ok"

    def test_all_steps_fail_returns_none(self, tmp_path, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        with patch("mosaic.sources.unpaywall.resolve", return_value=None), \
             patch("mosaic.auth.find_session_for_url", return_value=None):
            result = download(p, str(tmp_path), tmp_cache, unpaywall_email="me@uni.edu")
        assert result is None
