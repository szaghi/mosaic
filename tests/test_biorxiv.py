"""Tests for BioRxivSource — search page + content API."""

from unittest.mock import MagicMock, patch

from mosaic.models import SearchFilters
from mosaic.sources.biorxiv import _DOI_HREF_RE, BioRxivSource

# ── fixtures / helpers ────────────────────────────────────────────────────────

# Minimal search-results HTML containing two biorxiv DOI hrefs
_SEARCH_HTML = """\
<html><body>
<li class="search-result">
  <a href="/content/10.1101/2023.01.15.524150v2">Title One</a>
</li>
<li class="search-result">
  <a href="/content/10.1101/2022.06.10.495673v1">Title Two</a>
</li>
</body></html>
"""


# bioRxiv content API response for a single DOI
def _api_resp(doi, title, version="1", year="2023", abstract="An abstract."):
    return {
        "messages": [{"status": "ok", "total": 1, "cursor": "0", "count": 1}],
        "collection": [
            {
                "doi": doi,
                "title": title,
                "authors": "Smith J; Jones A",
                "date": f"{year}-01-15",
                "version": version,
                "category": "bioinformatics",
                "abstract": abstract,
                "server": "biorxiv",
            }
        ],
    }


def _make_resp(status=200, text="", json_data=None):
    m = MagicMock()
    m.status_code = status
    m.text = text
    if json_data is not None:
        m.json.return_value = json_data
    return m


# ── DOI regex ─────────────────────────────────────────────────────────────────


class TestDoiHrefRegex:
    def test_matches_versioned_href(self):
        html = '<a href="/content/10.1101/2023.01.15.524150v2">'
        assert _DOI_HREF_RE.search(html).group(1) == "10.1101/2023.01.15.524150"

    def test_matches_unversioned_href(self):
        html = '<a href="/content/10.1101/2022.06.10.495673">'
        assert _DOI_HREF_RE.search(html).group(1) == "10.1101/2022.06.10.495673"

    def test_no_match_on_unrelated_href(self):
        html = '<a href="/about/biorxiv">'
        assert _DOI_HREF_RE.search(html) is None

    def test_deduplicates_versions(self):
        html = (
            '<a href="/content/10.1101/2023.01.15.524150v1">'
            '<a href="/content/10.1101/2023.01.15.524150v2">'
        )
        dois = [m.group(1) for m in _DOI_HREF_RE.finditer(html)]
        # Both match but with the same DOI (version stripped)
        assert dois == ["10.1101/2023.01.15.524150", "10.1101/2023.01.15.524150"]


# ── _parse ────────────────────────────────────────────────────────────────────


class TestParse:
    src = BioRxivSource()

    def test_basic_fields(self):
        item = {
            "doi": "10.1101/2023.01.15.524150",
            "title": "A Great Preprint",
            "authors": "Smith J; Jones A",
            "date": "2023-01-15",
            "version": "2",
            "category": "bioinformatics",
            "abstract": "Abstract here.",
        }
        p = self.src._parse(item, "biorxiv")
        assert p.title == "A Great Preprint"
        assert p.authors == ["Smith J", "Jones A"]
        assert p.year == 2023
        assert p.doi == "10.1101/2023.01.15.524150"
        assert p.abstract == "Abstract here."
        assert p.is_open_access is True
        assert p.source == "bioRxiv/medRxiv"

    def test_pdf_url_constructed_from_doi_and_version(self):
        item = {
            "doi": "10.1101/2023.01.15.524150",
            "title": "T",
            "version": "3",
            "date": "2023-01-15",
            "authors": "A B",
            "category": "",
        }
        p = self.src._parse(item, "biorxiv")
        assert p.pdf_url == "https://www.biorxiv.org/content/10.1101/2023.01.15.524150v3.full.pdf"

    def test_medrxiv_server_in_url(self):
        item = {
            "doi": "10.1101/2022.06.10.495673",
            "title": "T",
            "version": "1",
            "date": "2022-06-10",
            "authors": "X Y",
            "category": "infectious diseases",
        }
        p = self.src._parse(item, "medrxiv")
        assert "medrxiv.org" in p.url
        assert "medrxiv.org" in p.pdf_url

    def test_category_in_journal(self):
        item = {
            "doi": "10.1101/2023.01.15.524150",
            "title": "T",
            "version": "1",
            "date": "2023-01-15",
            "authors": "A",
            "category": "neuroscience",
        }
        p = self.src._parse(item, "biorxiv")
        assert p.journal == "Biorxiv [neuroscience]"

    def test_empty_category_gives_plain_journal(self):
        item = {
            "doi": "10.1101/2023.01.15.524150",
            "title": "T",
            "version": "1",
            "date": "2023-01-15",
            "authors": "A",
            "category": "",
        }
        p = self.src._parse(item, "biorxiv")
        assert p.journal == "Biorxiv"

    def test_missing_doi_gives_none(self):
        item = {
            "doi": "",
            "title": "T",
            "version": "1",
            "date": "2023-01-15",
            "authors": "A",
            "category": "",
        }
        p = self.src._parse(item, "biorxiv")
        assert p.doi is None
        assert p.pdf_url is None
        assert p.url is None

    def test_missing_date_year_is_none(self):
        item = {
            "doi": "10.1101/2023.01.15.524150",
            "title": "T",
            "version": "1",
            "date": "",
            "authors": "A",
            "category": "",
        }
        p = self.src._parse(item, "biorxiv")
        assert p.year is None


# ── _build_query ──────────────────────────────────────────────────────────────


class TestBuildQuery:
    def test_plain_query(self):
        q = BioRxivSource._build_query("deep learning", None)
        assert q == "deep learning"

    def test_year_from_added(self):
        f = SearchFilters(year_from=2020)
        q = BioRxivSource._build_query("CRISPR", f)
        assert "after:2019-12-31" in q

    def test_year_to_added(self):
        f = SearchFilters(year_to=2022)
        q = BioRxivSource._build_query("RNA", f)
        assert "before:2023-01-01" in q

    def test_author_appended(self):
        f = SearchFilters(authors=["Smith", "Jones"])
        q = BioRxivSource._build_query("protein", f)
        assert "author1:Smith" in q
        assert "author1:Jones" in q

    def test_raw_query_overrides(self):
        f = SearchFilters(raw_query="my raw query")
        q = BioRxivSource._build_query("ignored", f)
        assert q == "my raw query"

    def test_years_list_uses_min_max(self):
        f = SearchFilters(years=[2019, 2021, 2023])
        q = BioRxivSource._build_query("AI", f)
        assert "after:2018-12-31" in q
        assert "before:2024-01-01" in q


# ── _fetch_paper ──────────────────────────────────────────────────────────────


class TestFetchPaper:
    src = BioRxivSource()
    doi = "10.1101/2023.01.15.524150"

    def test_returns_paper_on_success(self):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_resp(json_data=_api_resp(self.doi, "Great Paper"))
        p = self.src._fetch_paper(mock_client, "biorxiv", self.doi)
        assert p is not None
        assert p.title == "Great Paper"

    def test_returns_none_on_non_200(self):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_resp(status=404)
        p = self.src._fetch_paper(mock_client, "biorxiv", self.doi)
        assert p is None

    def test_returns_none_on_empty_collection(self):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_resp(json_data={"messages": [], "collection": []})
        p = self.src._fetch_paper(mock_client, "biorxiv", self.doi)
        assert p is None

    def test_returns_none_on_exception(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("timeout")
        p = self.src._fetch_paper(mock_client, "biorxiv", self.doi)
        assert p is None

    def test_picks_latest_version(self):
        resp = {
            "collection": [
                {
                    "doi": self.doi,
                    "title": "v1",
                    "version": "1",
                    "date": "2023-01-01",
                    "authors": "A",
                    "category": "",
                },
                {
                    "doi": self.doi,
                    "title": "v2",
                    "version": "2",
                    "date": "2023-02-01",
                    "authors": "A",
                    "category": "",
                },
            ]
        }
        mock_client = MagicMock()
        mock_client.get.return_value = _make_resp(json_data=resp)
        p = self.src._fetch_paper(mock_client, "biorxiv", self.doi)
        assert p.title == "v2"


# ── search (integration-style) ────────────────────────────────────────────────


class TestSearch:
    src = BioRxivSource()

    def _mock_client_se(self, server_html=None, api_json=None, search_status=200):
        """Return a (client_cls, mock_client) tuple with a side_effect callable for .get()."""

        def side_effect(url, **kwargs):
            if "/search/" in url:
                return _make_resp(
                    status=search_status,
                    text=server_html or _SEARCH_HTML,
                )
            return _make_resp(
                json_data=api_json or _api_resp("10.1101/2023.01.15.524150", "Title One")
            )

        mock_client = MagicMock()
        mock_client.get.side_effect = side_effect
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)
        client_cls = MagicMock(return_value=ctx)
        return client_cls, mock_client

    def test_returns_papers_from_both_servers(self):
        doi1 = "10.1101/2023.01.15.524150"
        doi2 = "10.1101/2022.06.10.495673"

        def side_effect(url, **kwargs):
            if "/search/" in url:
                return _make_resp(text=_SEARCH_HTML)
            if doi1 in url:
                return _make_resp(json_data=_api_resp(doi1, "Title One"))
            return _make_resp(json_data=_api_resp(doi2, "Title Two"))

        mock_client = MagicMock()
        mock_client.get.side_effect = side_effect
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)
        client_cls = MagicMock(return_value=ctx)

        with patch("httpx.Client", client_cls):
            papers = self.src.search("transformer", max_results=5)

        titles = {p.title for p in papers}
        assert "Title One" in titles

    def test_search_page_failure_skips_server(self):
        def side_effect(url, **kwargs):
            if "biorxiv.org/search" in url:
                return _make_resp(status=503)
            if "medrxiv.org/search" in url:
                return _make_resp(text=_SEARCH_HTML)
            return _make_resp(json_data=_api_resp("10.1101/2023.01.15.524150", "medRxiv Paper"))

        mock_client = MagicMock()
        mock_client.get.side_effect = side_effect
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)
        client_cls = MagicMock(return_value=ctx)

        with patch("httpx.Client", client_cls):
            papers = self.src.search("covid", max_results=5)

        assert any("medRxiv Paper" in p.title for p in papers)

    def test_all_search_pages_fail_returns_empty(self):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_resp(status=500)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)
        client_cls = MagicMock(return_value=ctx)

        with patch("httpx.Client", client_cls):
            papers = self.src.search("deep learning", max_results=5)
        assert papers == []

    def test_year_filter_applied_to_query_url(self):
        filters = SearchFilters(year_from=2022, year_to=2023)
        captured_urls = []

        def side_effect(url, **kwargs):
            captured_urls.append(url)
            if "/search/" in url:
                return _make_resp(text="")  # no results
            return _make_resp(json_data={"collection": []})

        mock_client = MagicMock()
        mock_client.get.side_effect = side_effect
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)
        client_cls = MagicMock(return_value=ctx)

        with patch("httpx.Client", client_cls):
            self.src.search("RNA", max_results=5, filters=filters)

        search_urls = [u for u in captured_urls if "/search/" in u]
        assert all("after%3A2021-12-31" in u or "after:2021-12-31" in u for u in search_urls)

    def test_author_filter_removes_non_matching(self):
        doi = "10.1101/2023.01.15.524150"

        def side_effect(url, **kwargs):
            if "/search/" in url:
                return _make_resp(text=_SEARCH_HTML)
            return _make_resp(json_data=_api_resp(doi, "Paper"))

        mock_client = MagicMock()
        mock_client.get.side_effect = side_effect
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)
        client_cls = MagicMock(return_value=ctx)

        filters = SearchFilters(authors=["Nonexistent"])
        with patch("httpx.Client", client_cls):
            papers = self.src.search("RNA", max_results=5, filters=filters)

        assert papers == []

    def test_available_always_true(self):
        assert self.src.available() is True
