"""Tests for each search source: query building and response parsing."""
from unittest.mock import patch, MagicMock
from mosaic.models import SearchFilters

# ── helpers ──────────────────────────────────────────────────────────────────

_ARXIV_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <published>2017-06-12T00:00:00Z</published>
    <summary>We propose the Transformer.</summary>
    <link rel="related" title="pdf" href="http://arxiv.org/pdf/1706.03762v5"/>
    <arxiv:doi>10.48550/arXiv.1706.03762</arxiv:doi>
    <arxiv:journal_ref>NeurIPS 2017</arxiv:journal_ref>
  </entry>
</feed>"""

_SS_JSON = {
    "data": [{
        "paperId": "abc123",
        "title": "Attention Is All You Need",
        "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
        "year": 2017,
        "abstract": "We propose the Transformer.",
        "externalIds": {"DOI": "10.48550/arXiv.1706.03762", "ArXiv": "1706.03762"},
        "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
        "publicationVenue": {"name": "NeurIPS"},
        "journal": {"name": "NeurIPS 2017"},
        "isOpenAccess": True,
    }]
}

_SD_JSON = {
    "results": [{
        "title": "Deep Learning Review",
        "doi": "10.1016/j.test.2020.01",
        "pii": "S0000001",
        "sourceTitle": "Journal of AI",
        "publicationDate": "2020-03-15",
        "openAccess": True,
        "authors": [{"name": "John Smith"}],
        "pages": {"first": "1", "last": "12"},
        "uri": "https://www.sciencedirect.com/article/test",
        "volumeIssue": "Vol. 10",
    }]
}

_EPMC_JSON = {
    "resultList": {"result": [{
        "id": "12345",
        "source": "MED",
        "title": "RNA Sequencing Methods",
        "authorString": "Smith J, Doe J",
        "pubYear": "2021",
        "doi": "10.1093/nar/test",
        "abstractText": "A review of RNA-seq methods.",
        "journalTitle": "Nucleic Acids Research",
        "journalVolume": "49",
        "issue": "3",
        "pageInfo": "1234-1250",
        "isOpenAccess": "Y",
        "pmcid": "PMC12345",
    }]}
}

_DOAJ_JSON = {
    "results": [{
        "id": "doaj001",
        "bibjson": {
            "title": "Open Access Study",
            "abstract": "An open access abstract.",
            "year": "2022",
            "author": [{"name": "Alice Smith"}],
            "journal": {"title": "PLOS ONE", "volume": "17", "number": "3"},
            "identifier": [{"type": "doi", "id": "10.1371/test.001"}],
            "link": [{"type": "fulltext", "content_type": "PDF",
                      "url": "https://plos.org/pdf/test.pdf"}],
        }
    }]
}


def _mock_get(text="", json_data=None, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.text = text
    m.json.return_value = json_data or {}
    m.raise_for_status = MagicMock()
    return m


# ── arXiv ────────────────────────────────────────────────────────────────────

class TestArxivSource:
    def _source(self):
        from mosaic.sources.arxiv import ArxivSource
        return ArxivSource(delay=0)

    def test_parses_paper_fields(self):
        with patch("httpx.get", return_value=_mock_get(text=_ARXIV_XML)):
            papers = self._source().search("attention")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Attention Is All You Need"
        assert "Ashish Vaswani" in p.authors
        assert p.year == 2017
        assert p.doi == "10.48550/arXiv.1706.03762"
        assert p.pdf_url == "http://arxiv.org/pdf/1706.03762v5"
        assert p.journal == "NeurIPS 2017"
        assert p.is_open_access is True

    def test_year_filter_appended_to_query(self):
        f = SearchFilters(year_from=2017, year_to=2017)
        with patch("httpx.get", return_value=_mock_get(text="<feed/>")) as mock:
            self._source().search("attention", filters=f)
        query = mock.call_args.kwargs["params"]["search_query"]
        assert "submittedDate" in query
        assert "20170101" in query

    def test_author_filter_appended_to_query(self):
        f = SearchFilters(authors=["Vaswani"])
        with patch("httpx.get", return_value=_mock_get(text="<feed/>")) as mock:
            self._source().search("attention", filters=f)
        query = mock.call_args.kwargs["params"]["search_query"]
        assert "au:Vaswani" in query

    def test_journal_filter_appended_to_query(self):
        f = SearchFilters(journal="NeurIPS")
        with patch("httpx.get", return_value=_mock_get(text="<feed/>")) as mock:
            self._source().search("attention", filters=f)
        query = mock.call_args.kwargs["params"]["search_query"]
        assert "jr:NeurIPS" in query

    def test_doi_fallback_to_arxiv_doi(self):
        xml = _ARXIV_XML.replace(
            "<arxiv:doi>10.48550/arXiv.1706.03762</arxiv:doi>", ""
        )
        with patch("httpx.get", return_value=_mock_get(text=xml)):
            papers = self._source().search("attention")
        assert papers[0].doi == "10.48550/arXiv.1706.03762"

    def test_field_title_uses_ti_prefix(self):
        f = SearchFilters(field="title")
        with patch("httpx.get", return_value=_mock_get(text="<feed/>")) as mock:
            self._source().search("attention", filters=f)
        query = mock.call_args.kwargs["params"]["search_query"]
        assert query.startswith("ti:attention")

    def test_field_abstract_uses_abs_prefix(self):
        f = SearchFilters(field="abstract")
        with patch("httpx.get", return_value=_mock_get(text="<feed/>")) as mock:
            self._source().search("attention", filters=f)
        query = mock.call_args.kwargs["params"]["search_query"]
        assert query.startswith("abs:attention")

    def test_raw_query_overrides_field_transform(self):
        f = SearchFilters(raw_query="ti:transformers AND au:Vaswani")
        with patch("httpx.get", return_value=_mock_get(text="<feed/>")) as mock:
            self._source().search("attention", filters=f)
        query = mock.call_args.kwargs["params"]["search_query"]
        assert query == "ti:transformers AND au:Vaswani"


# ── Semantic Scholar ──────────────────────────────────────────────────────────

class TestSemanticScholarSource:
    def _source(self):
        from mosaic.sources.semantic_scholar import SemanticScholarSource
        return SemanticScholarSource()

    def test_parses_paper_fields(self):
        with patch("httpx.get", return_value=_mock_get(json_data=_SS_JSON)):
            papers = self._source().search("attention")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Attention Is All You Need"
        assert p.year == 2017
        assert p.doi == "10.48550/arXiv.1706.03762"
        assert p.arxiv_id == "1706.03762"
        assert p.pdf_url == "https://arxiv.org/pdf/1706.03762"
        assert p.is_open_access is True

    def test_year_range_sent_as_param(self):
        f = SearchFilters(year_from=2016, year_to=2020)
        with patch("httpx.get", return_value=_mock_get(json_data={"data": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["year"] == "2016-2020"

    def test_single_year_sent_without_dash(self):
        f = SearchFilters(year_from=2017, year_to=2017)
        with patch("httpx.get", return_value=_mock_get(json_data={"data": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["year"] == "2017"

    def test_no_year_filter_no_year_param(self):
        with patch("httpx.get", return_value=_mock_get(json_data={"data": []})) as mock:
            self._source().search("attention")
        params = mock.call_args.kwargs["params"]
        assert "year" not in params

    def test_raw_query_overrides_default(self):
        f = SearchFilters(raw_query="neural networks survey")
        with patch("httpx.get", return_value=_mock_get(json_data={"data": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["query"] == "neural networks survey"


# ── ScienceDirect ─────────────────────────────────────────────────────────────

class TestScienceDirectSource:
    def _source(self):
        from mosaic.sources.sciencedirect import ScienceDirectSource
        return ScienceDirectSource(api_key="test-key")

    def test_unavailable_without_api_key(self):
        from mosaic.sources.sciencedirect import ScienceDirectSource
        assert not ScienceDirectSource(api_key="").available()

    def test_available_with_api_key(self):
        assert self._source().available()

    def test_parses_paper_fields(self):
        with patch("httpx.put", return_value=_mock_get(json_data=_SD_JSON)):
            papers = self._source().search("deep learning")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Deep Learning Review"
        assert p.doi == "10.1016/j.test.2020.01"
        assert p.year == 2020
        assert p.journal == "Journal of AI"
        assert p.is_open_access is True
        assert p.pdf_url is not None

    def test_filters_added_to_body(self):
        f = SearchFilters(year_from=2020, year_to=2022, authors=["Smith"], journal="Nature")
        with patch("httpx.put", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("q", filters=f)
        body = mock.call_args.kwargs["json"]
        assert body["date"] == "2020-2022"
        assert "Smith" in body["authors"]
        assert body["pub"] == "Nature"

    def test_oa_filter_always_set(self):
        with patch("httpx.put", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("q")
        body = mock.call_args.kwargs["json"]
        assert body["filters"]["openAccess"] is True

    def test_field_title_uses_TITLE_syntax(self):
        f = SearchFilters(field="title")
        with patch("httpx.put", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("deep learning", filters=f)
        body = mock.call_args.kwargs["json"]
        assert body["qs"] == "TITLE(deep learning)"

    def test_field_abstract_uses_ABS_syntax(self):
        f = SearchFilters(field="abstract")
        with patch("httpx.put", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("deep learning", filters=f)
        body = mock.call_args.kwargs["json"]
        assert body["qs"] == "ABS(deep learning)"

    def test_raw_query_overrides_qs(self):
        f = SearchFilters(raw_query="TITLE(transformers) AND AUTHOR(Vaswani)")
        with patch("httpx.put", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        body = mock.call_args.kwargs["json"]
        assert body["qs"] == "TITLE(transformers) AND AUTHOR(Vaswani)"


# ── Europe PMC ────────────────────────────────────────────────────────────────

class TestEuropePMCSource:
    def _source(self):
        from mosaic.sources.europepmc import EuropePMCSource
        return EuropePMCSource()

    def test_parses_paper_fields(self):
        with patch("httpx.get", return_value=_mock_get(json_data=_EPMC_JSON)):
            papers = self._source().search("RNA")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "RNA Sequencing Methods"
        assert "Smith J" in p.authors
        assert p.year == 2021
        assert p.doi == "10.1093/nar/test"
        assert p.is_open_access is True
        assert "PMC12345" in p.pdf_url

    def test_year_range_appended_to_query(self):
        f = SearchFilters(year_from=2020, year_to=2022)
        with patch("httpx.get", return_value=_mock_get(json_data={"resultList": {"result": []}})) as mock:
            self._source().search("RNA", filters=f)
        query = mock.call_args.kwargs["params"]["query"]
        assert "PUB_YEAR:[2020 TO 2022]" in query

    def test_author_appended_to_query(self):
        f = SearchFilters(authors=["Smith"])
        with patch("httpx.get", return_value=_mock_get(json_data={"resultList": {"result": []}})) as mock:
            self._source().search("RNA", filters=f)
        query = mock.call_args.kwargs["params"]["query"]
        assert 'AUTH:"Smith"' in query

    def test_journal_appended_to_query(self):
        f = SearchFilters(journal="Nature")
        with patch("httpx.get", return_value=_mock_get(json_data={"resultList": {"result": []}})) as mock:
            self._source().search("RNA", filters=f)
        query = mock.call_args.kwargs["params"]["query"]
        assert 'JOURNAL:"Nature"' in query

    def test_field_title_uses_TITLE_prefix(self):
        f = SearchFilters(field="title")
        with patch("httpx.get", return_value=_mock_get(json_data={"resultList": {"result": []}})) as mock:
            self._source().search("RNA", filters=f)
        query = mock.call_args.kwargs["params"]["query"]
        assert query.startswith('TITLE:"RNA"')

    def test_field_abstract_uses_ABSTRACT_prefix(self):
        f = SearchFilters(field="abstract")
        with patch("httpx.get", return_value=_mock_get(json_data={"resultList": {"result": []}})) as mock:
            self._source().search("RNA", filters=f)
        query = mock.call_args.kwargs["params"]["query"]
        assert query.startswith('ABSTRACT:"RNA"')

    def test_raw_query_overrides_field_transform(self):
        f = SearchFilters(raw_query="TITLE:CRISPR AND AUTH:Zhang")
        with patch("httpx.get", return_value=_mock_get(json_data={"resultList": {"result": []}})) as mock:
            self._source().search("RNA", filters=f)
        query = mock.call_args.kwargs["params"]["query"]
        assert query == "TITLE:CRISPR AND AUTH:Zhang"


# ── DOAJ ──────────────────────────────────────────────────────────────────────

class TestDoajSource:
    def _source(self):
        from mosaic.sources.doaj import DoajSource
        return DoajSource()

    def test_parses_paper_fields(self):
        with patch("httpx.get", return_value=_mock_get(json_data=_DOAJ_JSON)):
            papers = self._source().search("open access")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Open Access Study"
        assert p.year == 2022
        assert p.doi == "10.1371/test.001"
        assert p.journal == "PLOS ONE"
        assert p.pdf_url == "https://plos.org/pdf/test.pdf"
        assert p.is_open_access is True

    def test_author_filter_in_query(self):
        f = SearchFilters(authors=["Alice"])
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("test", filters=f)
        url = str(mock.call_args.args[0])
        assert "Alice" in url

    def test_year_range_filter_in_query(self):
        f = SearchFilters(year_from=2020, year_to=2022)
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("test", filters=f)
        url = str(mock.call_args.args[0])
        assert "2020" in url

    def test_field_title_uses_bibjson_title(self):
        f = SearchFilters(field="title")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("CRISPR", filters=f)
        url = str(mock.call_args.args[0])
        assert "bibjson.title" in url

    def test_field_abstract_uses_bibjson_abstract(self):
        f = SearchFilters(field="abstract")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("CRISPR", filters=f)
        url = str(mock.call_args.args[0])
        assert "bibjson.abstract" in url

    def test_raw_query_overrides_field_transform(self):
        f = SearchFilters(raw_query="bibjson.title:CRISPR AND bibjson.author.name:Zhang")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("CRISPR", filters=f)
        url = str(mock.call_args.args[0])
        assert "bibjson.title%3ACRISPR" in url or "bibjson.title:CRISPR" in url


_OPENALEX_JSON = {
    "results": [{
        "id": "https://openalex.org/W2741809807",
        "title": "Attention Is All You Need",
        "authorships": [
            {"author": {"display_name": "Ashish Vaswani"}},
            {"author": {"display_name": "Noam Shazeer"}},
        ],
        "publication_year": 2017,
        "doi": "https://doi.org/10.48550/arxiv.1706.03762",
        "ids": {"arxiv": "https://arxiv.org/abs/1706.03762"},
        "abstract_inverted_index": {"We": [0], "propose": [1], "the": [2], "Transformer.": [3]},
        "primary_location": {
            "source": {"display_name": "NeurIPS"},
            "pdf_url": None,
        },
        "best_oa_location": {"pdf_url": "https://arxiv.org/pdf/1706.03762"},
        "open_access": {"is_oa": True},
        "biblio": {"volume": "30", "issue": "1", "first_page": "1", "last_page": "11"},
    }]
}


# ── OpenAlex ──────────────────────────────────────────────────────────────────

class TestOpenAlexSource:
    def _source(self, email=""):
        from mosaic.sources.openalex import OpenAlexSource
        return OpenAlexSource(email=email)

    def test_parses_paper_fields(self):
        with patch("httpx.get", return_value=_mock_get(json_data=_OPENALEX_JSON)):
            papers = self._source().search("attention")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Attention Is All You Need"
        assert "Ashish Vaswani" in p.authors
        assert p.year == 2017
        assert p.doi == "10.48550/arxiv.1706.03762"
        assert p.arxiv_id == "1706.03762"
        assert p.abstract == "We propose the Transformer."
        assert p.journal == "NeurIPS"
        assert p.pdf_url == "https://arxiv.org/pdf/1706.03762"
        assert p.is_open_access is True
        assert p.pages == "1-11"
        assert p.url == "https://openalex.org/W2741809807"

    def test_year_filter_sent_as_filter_param(self):
        f = SearchFilters(year_from=2016, year_to=2020)
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["filter"] == "publication_year:2016-2020"

    def test_explicit_year_list_uses_min_max(self):
        f = SearchFilters(years=[2017, 2019, 2021])
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["filter"] == "publication_year:2017-2021"

    def test_no_filter_param_without_year(self):
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention")
        params = mock.call_args.kwargs["params"]
        assert "filter" not in params

    def test_mailto_sent_when_email_provided(self):
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source(email="test@example.com").search("attention")
        params = mock.call_args.kwargs["params"]
        assert params["mailto"] == "test@example.com"

    def test_no_mailto_without_email(self):
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention")
        params = mock.call_args.kwargs["params"]
        assert "mailto" not in params

    def test_field_title_uses_filter_title_search(self):
        f = SearchFilters(field="title")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params.get("filter") == "title.search:attention"
        assert "search" not in params

    def test_field_abstract_uses_filter_abstract_search(self):
        f = SearchFilters(field="abstract")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params.get("filter") == "abstract.search:attention"

    def test_raw_query_uses_search_param(self):
        f = SearchFilters(raw_query="title.search:transformers")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params.get("search") == "title.search:transformers"

    def test_field_title_with_year_merges_filter(self):
        f = SearchFilters(field="title", year_from=2020, year_to=2022)
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert "title.search:attention" in params["filter"]
        assert "publication_year:2020-2022" in params["filter"]


_BASE_JSON = {
    "response": {
        "numFound": 1,
        "docs": [{
            "dctitle": "Attention Is All You Need",
            "dccreator": ["Ashish Vaswani", "Noam Shazeer"],
            "dcyear": "2017",
            "dcdoi": "10.48550/arxiv.1706.03762",
            "dcdescription": "We propose the Transformer.",
            "dcsource": "NeurIPS",
            "dclink": "https://arxiv.org/pdf/1706.03762",
            "dcoa": 1,
            "dcformat": "application/pdf",
        }]
    }
}


# ── BASE ──────────────────────────────────────────────────────────────────────

class TestBASESource:
    def _source(self):
        from mosaic.sources.base_search import BASESource
        return BASESource()

    def test_parses_paper_fields(self):
        with patch("httpx.get", return_value=_mock_get(json_data=_BASE_JSON)):
            papers = self._source().search("attention")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Attention Is All You Need"
        assert "Ashish Vaswani" in p.authors
        assert p.year == 2017
        assert p.doi == "10.48550/arxiv.1706.03762"
        assert p.abstract == "We propose the Transformer."
        assert p.journal == "NeurIPS"
        assert p.is_open_access is True
        assert p.pdf_url == "https://arxiv.org/pdf/1706.03762"
        assert p.url == "https://arxiv.org/pdf/1706.03762"

    def test_no_pdf_url_when_not_oa(self):
        doc = {**_BASE_JSON["response"]["docs"][0], "dcoa": 0}
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": [doc]}})):
            papers = self._source().search("attention")
        assert papers[0].pdf_url is None
        assert papers[0].is_open_access is False

    def test_no_pdf_url_when_not_pdf_format(self):
        doc = {**_BASE_JSON["response"]["docs"][0], "dcformat": "text/html"}
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": [doc]}})):
            papers = self._source().search("attention")
        assert papers[0].pdf_url is None

    def test_handles_string_title(self):
        doc = {**_BASE_JSON["response"]["docs"][0], "dctitle": "Single String Title"}
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": [doc]}})):
            papers = self._source().search("attention")
        assert papers[0].title == "Single String Title"

    def test_year_range_filter_appended_to_query(self):
        f = SearchFilters(year_from=2016, year_to=2020)
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": []}})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert "dcyear:[2016 TO 2020]" in params["query"]

    def test_explicit_year_list_filter(self):
        f = SearchFilters(years=[2017, 2019])
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": []}})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert "dcyear:2017" in params["query"]
        assert "dcyear:2019" in params["query"]

    def test_author_filter_appended_to_query(self):
        f = SearchFilters(authors=["Vaswani"])
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": []}})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert 'dccreator:"Vaswani"' in params["query"]

    def test_journal_filter_appended_to_query(self):
        f = SearchFilters(journal="NeurIPS")
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": []}})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert 'dcsource:"NeurIPS"' in params["query"]

    def test_field_title_uses_dctitle_prefix(self):
        f = SearchFilters(field="title")
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": []}})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["query"].startswith('dctitle:"attention"')

    def test_field_abstract_uses_dcabstract_prefix(self):
        f = SearchFilters(field="abstract")
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": []}})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["query"].startswith('dcabstract:"attention"')

    def test_raw_query_overrides_field_transform(self):
        f = SearchFilters(raw_query="dctitle:transformers AND dccreator:Vaswani")
        with patch("httpx.get", return_value=_mock_get(json_data={"response": {"docs": []}})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["query"] == "dctitle:transformers AND dccreator:Vaswani"


_CORE_JSON = {
    "totalHits": 1,
    "results": [{
        "id": 2741809807,
        "title": "Attention Is All You Need",
        "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
        "yearPublished": 2017,
        "doi": "10.48550/arxiv.1706.03762",
        "abstract": "We propose the Transformer.",
        "journals": [{"title": "NeurIPS"}],
        "downloadUrl": "https://arxiv.org/pdf/1706.03762",
        "isOpenAccess": True,
    }]
}


# ── CORE ──────────────────────────────────────────────────────────────────────

class TestCORESource:
    def _source(self, api_key="test-key"):
        from mosaic.sources.core import CORESource
        return CORESource(api_key=api_key)

    def test_unavailable_without_api_key(self):
        from mosaic.sources.core import CORESource
        assert not CORESource(api_key="").available()

    def test_available_with_api_key(self):
        assert self._source().available()

    def test_parses_paper_fields(self):
        with patch("httpx.get", return_value=_mock_get(json_data=_CORE_JSON)):
            papers = self._source().search("attention")
        assert len(papers) == 1
        p = papers[0]
        assert p.title == "Attention Is All You Need"
        assert "Ashish Vaswani" in p.authors
        assert p.year == 2017
        assert p.doi == "10.48550/arxiv.1706.03762"
        assert p.abstract == "We propose the Transformer."
        assert p.journal == "NeurIPS"
        assert p.pdf_url == "https://arxiv.org/pdf/1706.03762"
        assert p.is_open_access is True
        assert p.url == "https://core.ac.uk/works/2741809807"

    def test_api_key_sent_in_auth_header(self):
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source(api_key="mykey").search("attention")
        headers = mock.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer mykey"

    def test_no_auth_header_without_key(self):
        from mosaic.sources.core import CORESource
        src = CORESource(api_key="")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            # call search directly (bypassing available() check)
            src.search("attention")
        headers = mock.call_args.kwargs["headers"]
        assert "Authorization" not in headers

    def test_year_range_filter_appended_to_query(self):
        f = SearchFilters(year_from=2016, year_to=2020)
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert "yearPublished>=2016" in params["q"]
        assert "yearPublished<=2020" in params["q"]

    def test_explicit_year_list_uses_min_max(self):
        f = SearchFilters(years=[2017, 2019, 2021])
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert "yearPublished>=2017" in params["q"]
        assert "yearPublished<=2021" in params["q"]

    def test_author_filter_appended_to_query(self):
        f = SearchFilters(authors=["Vaswani"])
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert 'authors.name:"Vaswani"' in params["q"]

    def test_journal_filter_appended_to_query(self):
        f = SearchFilters(journal="NeurIPS")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert 'journals.title:"NeurIPS"' in params["q"]

    def test_field_title_uses_title_prefix(self):
        f = SearchFilters(field="title")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["q"].startswith('title:"attention"')

    def test_field_abstract_uses_abstract_prefix(self):
        f = SearchFilters(field="abstract")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["q"].startswith('abstract:"attention"')

    def test_raw_query_overrides_field_transform(self):
        f = SearchFilters(raw_query="title:transformers AND authors.name:Vaswani")
        with patch("httpx.get", return_value=_mock_get(json_data={"results": []})) as mock:
            self._source().search("attention", filters=f)
        params = mock.call_args.kwargs["params"]
        assert params["q"] == "title:transformers AND authors.name:Vaswani"


# ── Unpaywall ─────────────────────────────────────────────────────────────────

class TestUnpaywall:
    def test_returns_pdf_url_when_oa(self):
        from mosaic.sources.unpaywall import resolve
        data = {"is_oa": True, "best_oa_location": {
            "url_for_pdf": "https://arxiv.org/pdf/1706.03762", "url": "https://arxiv.org/abs/1706.03762"
        }}
        with patch("httpx.get", return_value=_mock_get(json_data=data)):
            url = resolve("10.48550/arXiv.1706.03762", "test@example.com")
        assert url == "https://arxiv.org/pdf/1706.03762"

    def test_returns_none_when_not_oa(self):
        from mosaic.sources.unpaywall import resolve
        with patch("httpx.get", return_value=_mock_get(json_data={"is_oa": False})):
            assert resolve("10.1/paywalled", "test@example.com") is None

    def test_returns_none_without_email(self):
        from mosaic.sources.unpaywall import resolve
        assert resolve("10.1/x", "") is None

    def test_returns_none_on_http_error(self):
        from mosaic.sources.unpaywall import resolve
        m = MagicMock()
        m.status_code = 404
        m.json.side_effect = Exception("not found")
        with patch("httpx.get", return_value=m):
            assert resolve("10.1/x", "test@example.com") is None
