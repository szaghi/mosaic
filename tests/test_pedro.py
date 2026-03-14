"""Tests for PEDroSource — search-results page parsing and search logic."""

from unittest.mock import MagicMock, patch

import pytest

from mosaic.models import SearchFilters
from mosaic.sources.pedro import PEDroSource, _unescape

# ── HTML fixtures ─────────────────────────────────────────────────────────────

_SESSION_HTML = """\
<!DOCTYPE html><html><head>
<meta name="csrf-token" content="abc123">
</head><body><h2>Advanced Search</h2></body></html>
"""

_RESULTS_HTML = """\
<!DOCTYPE html><html><body>
<div id="search-content">
  Found 2 records
  <table class="search-results">
    <thead>
      <tr class="browse_header">
        <th>Title</th><th>Method</th><th>Score (/10)</th><th>Select Record</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><a href="https://search.pedro.org.au/search-results/record-detail/12345"
               class="left">Exercise therapy for chronic low back pain</a></td>
        <td>clinical trial</td>
        <td>8/10</td>
        <td class="hidden-narrow" id="art-12345">
          <a href="#" class="select" data-article-id="12345">Select</a>
        </td>
      </tr>
      <tr>
        <td><a href="https://search.pedro.org.au/search-results/record-detail/67890"
               class="left">Physiotherapy for knee osteoarthritis: a systematic review</a></td>
        <td>systematic review</td>
        <td>N/A</td>
        <td class="hidden-narrow" id="art-67890">
          <a href="#" class="select" data-article-id="67890">Select</a>
        </td>
      </tr>
    </tbody>
  </table>
</div>
</body></html>
"""

_EMPTY_HTML = """\
<!DOCTYPE html><html><body>
<div id="search-content">
  <h2>PEDro - No records found</h2>
  Sorry, no matches were found.
</div>
</body></html>
"""

_RESULTS_HTML_WITH_ENTITIES = """\
<!DOCTYPE html><html><body>
<table class="search-results"><tbody>
  <tr>
    <td><a href="https://search.pedro.org.au/search-results/record-detail/99"
           class="left">Japan&#039;s cancer survivorship guidelines &amp; exercise</a></td>
    <td>practice guideline</td>
    <td>N/A</td>
    <td></td>
  </tr>
</tbody></table>
</body></html>
"""


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_resp(status=200, text=""):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.raise_for_status = MagicMock()
    return m


def _mock_client(session_text=_SESSION_HTML, results_text=_RESULTS_HTML):
    """Return a mock httpx.Client whose .get() yields session then results."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = [
        _make_resp(text=session_text),
        _make_resp(text=results_text),
    ]
    return client


# ── _unescape ─────────────────────────────────────────────────────────────────


class TestUnescape:
    def test_apostrophe_numeric(self):
        assert _unescape("Japan&#039;s") == "Japan's"

    def test_amp(self):
        assert _unescape("A &amp; B") == "A & B"

    def test_lt_gt(self):
        assert _unescape("&lt;em&gt;") == "<em>"

    def test_quot(self):
        assert _unescape("&quot;quoted&quot;") == '"quoted"'

    def test_no_entities(self):
        assert _unescape("plain text") == "plain text"


# ── _parse_page ───────────────────────────────────────────────────────────────


class TestParsePage:
    def test_returns_two_papers(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert len(papers) == 2

    def test_title_populated(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert papers[0].title == "Exercise therapy for chronic low back pain"

    def test_second_title_populated(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert papers[1].title == "Physiotherapy for knee osteoarthritis: a systematic review"

    def test_url_is_record_detail(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert "record-detail/12345" in papers[0].url
        assert "record-detail/67890" in papers[1].url

    def test_journal_is_method(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert papers[0].journal == "Clinical Trial"
        assert papers[1].journal == "Systematic Review"

    def test_score_in_abstract(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert "PEDro score: 8/10" in papers[0].abstract

    def test_na_score_not_in_abstract(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert "PEDro score" not in (papers[1].abstract or "")

    def test_source_is_pedro(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert all(p.source == "PEDro" for p in papers)

    def test_authors_empty_list(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert all(p.authors == [] for p in papers)

    def test_year_is_none(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert all(p.year is None for p in papers)

    def test_doi_is_none(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert all(p.doi is None for p in papers)

    def test_is_open_access_false(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML)
        assert all(not p.is_open_access for p in papers)

    def test_empty_page_returns_empty_list(self):
        papers = PEDroSource._parse_page(_EMPTY_HTML)
        assert papers == []

    def test_no_table_returns_empty_list(self):
        papers = PEDroSource._parse_page("<html><body><p>nothing</p></body></html>")
        assert papers == []

    def test_html_entities_decoded_in_title(self):
        papers = PEDroSource._parse_page(_RESULTS_HTML_WITH_ENTITIES)
        assert papers[0].title == "Japan's cancer survivorship guidelines & exercise"


# ── available ─────────────────────────────────────────────────────────────────


class TestAvailable:
    def test_disabled_by_default(self):
        assert PEDroSource().available() is False

    def test_enabled_when_acknowledged(self):
        assert PEDroSource(acknowledge_fair_use=True).available() is True


# ── search ────────────────────────────────────────────────────────────────────


class TestSearch:
    src = PEDroSource(acknowledge_fair_use=True, rate_limit_delay=0)

    def test_returns_papers(self):
        with patch("httpx.Client", return_value=_mock_client()):
            papers = self.src.search("exercise", max_results=5)
        assert len(papers) == 2
        assert papers[0].title == "Exercise therapy for chronic low back pain"

    def test_session_url_called_first(self):
        mock_client = _mock_client()
        with patch("httpx.Client", return_value=mock_client):
            self.src.search("exercise", max_results=5)
        calls = mock_client.get.call_args_list
        assert "advanced-search" in calls[0][0][0]

    def test_search_url_called_second(self):
        mock_client = _mock_client()
        with patch("httpx.Client", return_value=mock_client):
            self.src.search("exercise", max_results=5)
        calls = mock_client.get.call_args_list
        assert "advanced-search/results" in calls[1][0][0]

    def test_query_in_params(self):
        mock_client = _mock_client()
        with patch("httpx.Client", return_value=mock_client):
            self.src.search("back pain", max_results=5)
        _, kwargs = mock_client.get.call_args_list[1]
        params = kwargs.get("params", {})
        assert params.get("abstract_with_title") == "back pain"

    def test_title_field_uses_title_param(self):
        mock_client = _mock_client(results_text=_EMPTY_HTML)
        filters = SearchFilters(field="title")
        with patch("httpx.Client", return_value=mock_client):
            self.src.search("low back pain", max_results=5, filters=filters)
        _, kwargs = mock_client.get.call_args_list[1]
        params = kwargs.get("params", {})
        assert "title" in params
        assert "abstract_with_title" not in params

    def test_year_from_in_params(self):
        mock_client = _mock_client(results_text=_EMPTY_HTML)
        filters = SearchFilters(year_from=2020)
        with patch("httpx.Client", return_value=mock_client):
            self.src.search("exercise", max_results=5, filters=filters)
        _, kwargs = mock_client.get.call_args_list[1]
        params = kwargs.get("params", {})
        assert params.get("year_of_publication") == 2020

    def test_max_results_limits_output(self):
        mock_client = _mock_client()
        with patch("httpx.Client", return_value=mock_client):
            papers = self.src.search("exercise", max_results=1)
        assert len(papers) == 1

    def test_empty_results_returns_empty_list(self):
        mock_client = _mock_client(results_text=_EMPTY_HTML)
        with patch("httpx.Client", return_value=mock_client):
            papers = self.src.search("xyzxyzxyz", max_results=5)
        assert papers == []

    def test_http_error_propagates(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        err_resp = _make_resp(status=503)
        err_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
        mock_client.get.side_effect = [_make_resp(text=_SESSION_HTML), err_resp]
        with patch("httpx.Client", return_value=mock_client):
            with pytest.raises(Exception, match="503"):
                self.src.search("exercise", max_results=5)

    def test_author_filter_removes_non_matching(self):
        mock_client = _mock_client()
        filters = SearchFilters(authors=["Nonexistent Author"])
        with patch("httpx.Client", return_value=mock_client):
            papers = self.src.search("exercise", max_results=5, filters=filters)
        assert papers == []

    def test_disabled_source_not_available(self):
        src = PEDroSource(acknowledge_fair_use=False)
        assert src.available() is False

    def test_rate_limit_delay_zero_does_not_sleep(self):
        """Verify a zero delay doesn't cause issues."""
        src = PEDroSource(acknowledge_fair_use=True, rate_limit_delay=0)
        mock_client = _mock_client()
        with patch("httpx.Client", return_value=mock_client):
            papers = src.search("exercise", max_results=5)
        assert len(papers) == 2

    def test_custom_delay_passed_to_sleep(self):
        src = PEDroSource(acknowledge_fair_use=True, rate_limit_delay=0.1)
        mock_client = _mock_client()
        with (
            patch("httpx.Client", return_value=mock_client),
            patch("mosaic.sources.pedro.time.sleep") as mock_sleep,
        ):
            src.search("exercise", max_results=5)
        # time.sleep called at least once (after session request)
        assert mock_sleep.call_count >= 1
        mock_sleep.assert_any_call(0.1)
