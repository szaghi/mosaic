"""Tests for mosaic/cite.py — citation formatting and metadata resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from mosaic.models import Paper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cr_response(item: dict, status: int = 200) -> MagicMock:
    """Build a mock httpx response shaped like a Crossref works/{doi} reply."""
    m = MagicMock()
    m.status_code = status
    m.json.return_value = {"message": item}
    if status >= 400:
        m.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=MagicMock(), response=m
        )
    else:
        m.raise_for_status = MagicMock()
    return m


def _make_cn_response(
    text: str, status: int = 200, content_type: str = "text/bibliography"
) -> MagicMock:
    """Build a mock httpx response shaped like a doi.org content-negotiation reply."""
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.headers = {"content-type": content_type}
    if status >= 400:
        m.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=MagicMock(), response=m
        )
    else:
        m.raise_for_status = MagicMock()
    return m


_CROSSREF_ITEM: dict = {
    "title": ["Attention Is All You Need"],
    "author": [{"given": "Ashish", "family": "Vaswani"}, {"given": "Noam", "family": "Shazeer"}],
    "published": {"date-parts": [[2017]]},
    "DOI": "10.48550/arxiv.1706.03762",
    "abstract": "The dominant sequence transduction models...",
    "container-title": ["Advances in Neural Information Processing Systems"],
    "URL": "https://doi.org/10.48550/arxiv.1706.03762",
    "volume": "30",
    "issue": None,
    "page": "5998-6008",
    "link": [{"content-type": "application/pdf", "URL": "https://arxiv.org/pdf/1706.03762"}],
}

_PAPER = Paper(
    title="Attention Is All You Need",
    authors=["Vaswani, Ashish", "Shazeer, Noam"],
    year=2017,
    doi="10.48550/arxiv.1706.03762",
    abstract="The dominant sequence transduction models...",
    journal="Advances in Neural Information Processing Systems",
    source="Crossref",
    is_open_access=True,
    pdf_url="https://arxiv.org/pdf/1706.03762",
)


# ---------------------------------------------------------------------------
# TestFetchPaperByDoi
# ---------------------------------------------------------------------------


class TestFetchPaperByDoi:
    def test_happy_path_returns_paper(self):
        from mosaic.cite import fetch_paper_by_doi

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cr_response(_CROSSREF_ITEM)

            paper = fetch_paper_by_doi("10.48550/arxiv.1706.03762")

        assert paper.title == "Attention Is All You Need"
        assert paper.year == 2017
        assert paper.doi == "10.48550/arxiv.1706.03762"
        assert paper.source == "Crossref"

    def test_email_added_to_params(self):
        from mosaic.cite import fetch_paper_by_doi

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cr_response(_CROSSREF_ITEM)

            fetch_paper_by_doi("10.48550/arxiv.1706.03762", email="user@example.com")

        _, kwargs = mock_client.get.call_args
        assert kwargs.get("params", {}).get("mailto") == "user@example.com"

    def test_no_email_omits_mailto(self):
        from mosaic.cite import fetch_paper_by_doi

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cr_response(_CROSSREF_ITEM)

            fetch_paper_by_doi("10.48550/arxiv.1706.03762")

        _, kwargs = mock_client.get.call_args
        assert "mailto" not in kwargs.get("params", {})

    def test_404_raises_http_status_error(self):
        from mosaic.cite import fetch_paper_by_doi

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cr_response({}, status=404)

            with pytest.raises(httpx.HTTPStatusError):
                fetch_paper_by_doi("10.9999/nonexistent")

    def test_network_error_propagates(self):
        from mosaic.cite import fetch_paper_by_doi

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = httpx.ConnectError("unreachable")

            with pytest.raises(httpx.ConnectError):
                fetch_paper_by_doi("10.1/x")

    def test_pdf_url_detected_from_link(self):
        from mosaic.cite import fetch_paper_by_doi

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cr_response(_CROSSREF_ITEM)

            paper = fetch_paper_by_doi("10.48550/arxiv.1706.03762")

        assert paper.pdf_url == "https://arxiv.org/pdf/1706.03762"
        assert paper.is_open_access is True

    def test_no_pdf_link_gives_none(self):
        from mosaic.cite import fetch_paper_by_doi

        item = {**_CROSSREF_ITEM, "link": []}
        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cr_response(item)

            paper = fetch_paper_by_doi("10.48550/arxiv.1706.03762")

        assert paper.pdf_url is None
        assert paper.is_open_access is False


# ---------------------------------------------------------------------------
# TestBibtexCitation
# ---------------------------------------------------------------------------


class TestBibtexCitation:
    def test_journal_paper_renders_article(self):
        from mosaic.cite import bibtex_citation

        result = bibtex_citation(_PAPER)
        assert result.startswith("@article{")

    def test_preprint_renders_misc(self):
        from mosaic.cite import bibtex_citation

        preprint = Paper(title="A Preprint", doi="10.1/x", source="arXiv", year=2023)
        result = bibtex_citation(preprint)
        assert result.startswith("@misc{")

    def test_doi_in_output(self):
        from mosaic.cite import bibtex_citation

        result = bibtex_citation(_PAPER)
        assert "10.48550/arxiv.1706.03762" in result

    def test_cite_key_contains_year(self):
        from mosaic.cite import bibtex_citation

        result = bibtex_citation(_PAPER)
        first_line = result.split("\n")[0]
        assert "2017" in first_line

    def test_title_in_output(self):
        from mosaic.cite import bibtex_citation

        result = bibtex_citation(_PAPER)
        assert "Attention Is All You Need" in result


# ---------------------------------------------------------------------------
# TestFetchFormattedCitation
# ---------------------------------------------------------------------------


class TestFetchFormattedCitation:
    def test_happy_path_returns_string(self):
        from mosaic.cite import fetch_formatted_citation

        expected = "Vaswani, A., et al. (2017). Attention is all you need."
        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cn_response(expected)

            result = fetch_formatted_citation("10.48550/arxiv.1706.03762", "apa")

        assert result == expected

    def test_style_in_accept_header(self):
        from mosaic.cite import fetch_formatted_citation

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cn_response("citation text")

            fetch_formatted_citation("10.1/x", "mla")

        _, kwargs = mock_client.get.call_args
        accept = kwargs.get("headers", {}).get("Accept", "")
        assert "style=mla" in accept

    def test_locale_en_us_in_accept_header(self):
        from mosaic.cite import fetch_formatted_citation

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cn_response("citation text")

            fetch_formatted_citation("10.1/x", "apa")

        _, kwargs = mock_client.get.call_args
        accept = kwargs.get("headers", {}).get("Accept", "")
        assert "locale=en-US" in accept

    def test_email_in_user_agent(self):
        from mosaic.cite import fetch_formatted_citation

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cn_response("citation text")

            fetch_formatted_citation("10.1/x", "apa", email="user@example.com")

        _, kwargs = mock_client.get.call_args
        ua = kwargs.get("headers", {}).get("User-Agent", "")
        assert "user@example.com" in ua

    def test_404_raises_http_status_error(self):
        from mosaic.cite import fetch_formatted_citation

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cn_response("", status=404)

            with pytest.raises(httpx.HTTPStatusError):
                fetch_formatted_citation("10.9999/bad", "apa")

    def test_result_is_stripped(self):
        from mosaic.cite import fetch_formatted_citation

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = _make_cn_response("  citation text  \n")

            result = fetch_formatted_citation("10.1/x", "chicago")

        assert result == "citation text"


# ---------------------------------------------------------------------------
# TestCopyToClipboard
# ---------------------------------------------------------------------------


class TestCopyToClipboard:
    def test_pyperclip_success(self):
        from mosaic.cite import copy_to_clipboard

        mock_pyperclip = MagicMock()
        with patch.dict("sys.modules", {"pyperclip": mock_pyperclip}):
            result = copy_to_clipboard("cite text")

        assert result is True
        mock_pyperclip.copy.assert_called_once_with("cite text")

    def test_pyperclip_missing_tries_subprocess(self):
        from mosaic.cite import copy_to_clipboard

        with patch.dict("sys.modules", {"pyperclip": None}):
            with patch("subprocess.run") as mock_run:
                result = copy_to_clipboard("cite text")

        assert result is True
        mock_run.assert_called_once()

    def test_subprocess_pbcopy_on_macos(self):
        from mosaic.cite import copy_to_clipboard

        with patch.dict("sys.modules", {"pyperclip": None}):
            with patch("sys.platform", "darwin"):
                with patch("subprocess.run") as mock_run:
                    result = copy_to_clipboard("cite text")

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd == ["pbcopy"]

    def test_subprocess_xclip_on_linux(self):
        from mosaic.cite import copy_to_clipboard

        with patch.dict("sys.modules", {"pyperclip": None}):
            with patch("sys.platform", "linux"):
                with patch("subprocess.run") as mock_run:
                    result = copy_to_clipboard("cite text")

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "xclip"

    def test_subprocess_clip_on_windows(self):
        from mosaic.cite import copy_to_clipboard

        with patch.dict("sys.modules", {"pyperclip": None}):
            with patch("sys.platform", "win32"):
                with patch("subprocess.run") as mock_run:
                    result = copy_to_clipboard("cite text")

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd == ["clip"]

    def test_all_methods_fail_returns_false(self):
        from mosaic.cite import copy_to_clipboard

        with patch.dict("sys.modules", {"pyperclip": None}):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = copy_to_clipboard("cite text")

        assert result is False


# ---------------------------------------------------------------------------
# TestResolvePaper
# ---------------------------------------------------------------------------


class TestResolvePaper:
    def test_cache_hit_returns_cached_paper(self):
        from mosaic.cite import resolve_paper

        mock_cache = MagicMock()
        mock_cache.get_by_uid.return_value = _PAPER

        result = resolve_paper("10.48550/arxiv.1706.03762", mock_cache)

        assert result is _PAPER
        mock_cache.save.assert_not_called()

    def test_cache_miss_fetches_from_crossref(self):
        from mosaic.cite import resolve_paper

        mock_cache = MagicMock()
        mock_cache.get_by_uid.return_value = None

        with patch("mosaic.cite.fetch_paper_by_doi", return_value=_PAPER) as mock_fetch:
            result = resolve_paper("10.48550/arxiv.1706.03762", mock_cache)

        mock_fetch.assert_called_once_with("10.48550/arxiv.1706.03762", "")
        assert result is _PAPER

    def test_cache_miss_saves_fetched_paper(self):
        from mosaic.cite import resolve_paper

        mock_cache = MagicMock()
        mock_cache.get_by_uid.return_value = None

        with patch("mosaic.cite.fetch_paper_by_doi", return_value=_PAPER):
            resolve_paper("10.48550/arxiv.1706.03762", mock_cache)

        mock_cache.save.assert_called_once_with(_PAPER)

    def test_email_forwarded_to_fetch(self):
        from mosaic.cite import resolve_paper

        mock_cache = MagicMock()
        mock_cache.get_by_uid.return_value = None

        with patch("mosaic.cite.fetch_paper_by_doi", return_value=_PAPER) as mock_fetch:
            resolve_paper("10.1/x", mock_cache, email="user@example.com")

        mock_fetch.assert_called_once_with("10.1/x", "user@example.com")

    def test_fetch_failure_propagates(self):
        from mosaic.cite import resolve_paper

        mock_cache = MagicMock()
        mock_cache.get_by_uid.return_value = None

        with patch(
            "mosaic.cite.fetch_paper_by_doi",
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock()),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                resolve_paper("10.9999/bad", mock_cache)
