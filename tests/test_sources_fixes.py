"""Regression tests for source-adapter fixes: retries, throttling, OR-ed authors,
field scoping, open-access detection, DOI normalisation and error propagation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mosaic.errors import SourceError
from mosaic.models import SearchFilters
from mosaic.sources.base import Throttle, any_of, phrase_if_needed, with_retry

# ── helpers ──────────────────────────────────────────────────────────────────


def _resp(json_data=None, text="", status=200, headers=None):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.headers = headers or {}
    m.json.return_value = json_data if json_data is not None else {}
    if status >= 400:
        request = httpx.Request("GET", "https://api.example.org/x?apikey=SECRET")
        response = httpx.Response(status, request=request)
        m.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"Client error '{status}' for url '{request.url}'", request=request, response=response
        )
    else:
        m.raise_for_status = MagicMock()
    return m


def _client(get=None, post=None, get_side_effect=None):
    mc = MagicMock()
    if get is not None:
        mc.get.return_value = get
    if post is not None:
        mc.post.return_value = post
    if get_side_effect is not None:
        mc.get.side_effect = get_side_effect
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mc)
    ctx.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=ctx), mc


@pytest.fixture(autouse=True)
def _no_sleep():
    """Retries and throttles must not slow the suite down."""
    with (
        patch("mosaic.sources.base.time.sleep") as sleep,
        patch("mosaic.sources.pubmed.NCBI_THROTTLE.wait"),
    ):
        yield sleep


# ── shared helpers ───────────────────────────────────────────────────────────


class TestQueryHelpers:
    def test_any_of_ors_values(self):
        assert any_of(["A", "B", "C"], "au:{}") == "(au:A OR au:B OR au:C)"

    def test_any_of_single_value_has_no_parentheses(self):
        assert any_of(["A"], "au:{}") == "au:A"

    def test_phrase_if_needed(self):
        assert phrase_if_needed("deep learning") == '"deep learning"'
        assert phrase_if_needed("single") == "single"
        assert phrase_if_needed("a OR b") == "a OR b"
        assert phrase_if_needed("(a b)") == "(a b)"


class TestWithRetry:
    def test_retries_on_429_then_succeeds(self, _no_sleep):
        send = MagicMock(side_effect=[_resp(status=429), _resp(status=200)])
        assert with_retry(send).status_code == 200
        assert send.call_count == 2
        _no_sleep.assert_called_once()

    def test_honours_retry_after_seconds_capped(self, _no_sleep):
        send = MagicMock(
            side_effect=[_resp(status=503, headers={"Retry-After": "120"}), _resp(status=200)]
        )
        with_retry(send)
        # capped to 10 s
        assert _no_sleep.call_args.args[0] == 10.0

    def test_gives_up_after_bounded_retries(self):
        send = MagicMock(return_value=_resp(status=429))
        resp = with_retry(send, retries=2)
        assert resp.status_code == 429
        assert send.call_count == 3

    def test_no_retry_on_other_errors(self):
        send = MagicMock(return_value=_resp(status=500))
        with_retry(send)
        assert send.call_count == 1

    def test_semantic_scholar_retries_429(self):
        from mosaic.sources.semantic_scholar import SemanticScholarSource

        cls, mc = _client()
        mc.get.side_effect = [_resp(status=429), _resp(json_data={"data": []})]
        with patch("httpx.Client", cls):
            assert SemanticScholarSource().search("x") == []
        assert mc.get.call_count == 2


class TestThrottle:
    def test_second_call_waits(self, _no_sleep):
        t = Throttle()
        with patch("mosaic.sources.base.time.monotonic", side_effect=[100.0, 100.0, 100.5, 101.0]):
            t.wait(3.0)  # first call: no wait
            t.wait(3.0)  # 0.5 s later: must wait 2.5 s
        assert _no_sleep.call_count == 1
        assert _no_sleep.call_args.args[0] == pytest.approx(2.5)

    def test_zero_interval_never_waits(self, _no_sleep):
        t = Throttle()
        t.wait(0)
        t.wait(0)
        _no_sleep.assert_not_called()

    def test_arxiv_throttle_shared_between_instances(self):
        from mosaic.sources import arxiv

        cls, mc = _client(get=_resp(text="<feed xmlns='http://www.w3.org/2005/Atom'/>"))
        with patch("httpx.Client", cls), patch.object(arxiv._THROTTLE, "wait") as wait:
            arxiv.ArxivSource(delay=3.0).search("a")
            arxiv.ArxivSource(delay=3.0).search("b")
        assert wait.call_count == 2
        assert all(c.args[0] == 3.0 for c in wait.call_args_list)


# ── arXiv ────────────────────────────────────────────────────────────────────


class TestArxivFixes:
    def _query(self, query="attention", **kw):
        from mosaic.sources.arxiv import ArxivSource

        cls, mc = _client(get=_resp(text="<feed xmlns='http://www.w3.org/2005/Atom'/>"))
        with patch("httpx.Client", cls):
            ArxivSource(delay=0).search(query, filters=SearchFilters(**kw) if kw else None)
        return mc.get.call_args.kwargs["params"]["search_query"]

    def test_authors_ored(self):
        q = self._query(authors=["Geoffrey Hinton", "LeCun"])
        assert 'AND (au:"Geoffrey Hinton" OR au:LeCun)' in q

    def test_multiword_title_scoped_as_phrase(self):
        assert self._query("deep learning", field="title") == 'ti:"deep learning"'

    def test_multiword_journal_quoted(self):
        assert 'jr:"Physical Review"' in self._query(journal="Physical Review")

    def test_old_style_id_version_strip(self):
        from mosaic.sources.arxiv import _NS, ArxivSource

        entry = ET.fromstring(
            f"""<entry xmlns="{_NS["atom"]}">
                  <id>http://arxiv.org/abs/solv-int/9901001v1</id>
                  <title>Old</title>
                </entry>"""
        )
        paper = ArxivSource(delay=0)._parse(entry)
        assert paper.doi == "10.48550/arXiv.solv-int/9901001"


# ── Lucene-style sources: authors OR-ed ─────────────────────────────────────


class TestAuthorsOred:
    def _params(self, source, response):
        cls, mc = _client(get=_resp(json_data=response))
        with patch("httpx.Client", cls):
            source.search("x", filters=SearchFilters(authors=["Ada Lovelace", "Alan Turing"]))
        return mc.get.call_args

    def test_europepmc(self):
        from mosaic.sources.europepmc import EuropePMCSource

        call = self._params(EuropePMCSource(), {"resultList": {"result": []}})
        assert 'AND (AUTH:"Ada Lovelace" OR AUTH:"Alan Turing")' in call.kwargs["params"]["query"]

    def test_base(self):
        from mosaic.sources.base_search import BASESource

        call = self._params(BASESource(), {"response": {"docs": []}})
        assert (
            '(dccreator:"Ada Lovelace" OR dccreator:"Alan Turing")'
            in call.kwargs["params"]["query"]
        )

    def test_core(self):
        from mosaic.sources.core import CORESource

        call = self._params(CORESource(api_key="k"), {"results": []})
        assert (
            '(authors.name:"Ada Lovelace" OR authors.name:"Alan Turing")'
            in call.kwargs["params"]["q"]
        )

    def test_zenodo(self):
        from mosaic.sources.zenodo import ZenodoSource

        call = self._params(ZenodoSource(), {"hits": {"hits": []}})
        assert (
            '(creators.name:"Ada Lovelace" OR creators.name:"Alan Turing")'
            in call.kwargs["params"]["q"]
        )

    def test_doaj(self):
        from mosaic.sources.doaj import DoajSource

        call = self._params(DoajSource(), {"results": []})
        # the query lives (percent-encoded) in the URL path
        from urllib.parse import unquote

        assert (
            '(bibjson.author.name:"Ada Lovelace" OR bibjson.author.name:"Alan Turing")'
            in unquote(call.args[0])
        )

    def test_pubmed(self):
        from mosaic.sources.pubmed import PubMedSource

        call = self._params(PubMedSource(), {"esearchresult": {"idlist": []}})
        assert '("Ada Lovelace"[au] OR "Alan Turing"[au])' in call.kwargs["params"]["term"]

    def test_pmc(self):
        from mosaic.sources.pmc import PMCSource

        call = self._params(PMCSource(), {"esearchresult": {"idlist": []}})
        assert '("Ada Lovelace"[au] OR "Alan Turing"[au])' in call.kwargs["params"]["term"]

    def test_quotes_in_author_escaped(self):
        from mosaic.sources.europepmc import EuropePMCSource

        cls, mc = _client(get=_resp(json_data={"resultList": {"result": []}}))
        with patch("httpx.Client", cls):
            EuropePMCSource().search("x", filters=SearchFilters(authors=['O"Brien']))
        assert 'AUTH:"O\\"Brien"' in mc.get.call_args.kwargs["params"]["query"]


# ── DOAJ ─────────────────────────────────────────────────────────────────────


class TestDoajFixes:
    @pytest.mark.parametrize("query", ["covid-19/sars", "c# language", "why? because"])
    def test_query_fully_percent_encoded_in_path(self, query):
        from mosaic.sources.doaj import DoajSource

        cls, mc = _client(get=_resp(json_data={"results": []}))
        with patch("httpx.Client", cls):
            DoajSource().search(query)
        url = mc.get.call_args.args[0]
        path_segment = url.removeprefix("https://doaj.org/api/v3/search/articles/")
        assert "/" not in path_segment
        assert "#" not in path_segment
        assert "?" not in path_segment

    def test_html_fulltext_link_not_used_as_pdf(self):
        from mosaic.sources.doaj import DoajSource

        item = {
            "id": "a1",
            "bibjson": {
                "title": "T",
                "link": [
                    {"type": "fulltext", "url": "https://j.org/html", "content_type": "HTML"},
                    {"type": "fulltext", "url": "https://j.org/a.pdf", "content_type": "PDF"},
                ],
            },
        }
        assert DoajSource()._parse(item).pdf_url == "https://j.org/a.pdf"

    def test_no_pdf_when_only_html(self):
        from mosaic.sources.doaj import DoajSource

        item = {"bibjson": {"title": "T", "link": [{"type": "fulltext", "url": "https://j/h"}]}}
        assert DoajSource()._parse(item).pdf_url is None


# ── NASA ADS ─────────────────────────────────────────────────────────────────


class TestNasaAdsPdfLink:
    def _pdf(self, props):
        from mosaic.sources.nasa_ads import NASAADSSource

        doc = {"title": ["T"], "bibcode": "2020ApJ...1..1A", "property": props}
        return NASAADSSource(api_key="k")._parse(doc).pdf_url

    def test_publisher_oa_uses_pub_pdf(self):
        assert self._pdf(["OPENACCESS", "PUB_OPENACCESS"]).endswith("/PUB_PDF")

    def test_eprint_only_oa_uses_eprint_pdf(self):
        assert self._pdf(["OPENACCESS", "EPRINT_OPENACCESS"]).endswith("/EPRINT_PDF")

    def test_not_oa_has_no_pdf(self):
        assert self._pdf(["REFEREED"]) is None

    def test_multiword_title_scope_quoted(self):
        from mosaic.sources.nasa_ads import NASAADSSource

        cls, mc = _client(get=_resp(json_data={"response": {"docs": []}}))
        with patch("httpx.Client", cls):
            NASAADSSource(api_key="k").search("dark matter", filters=SearchFilters(field="title"))
        assert mc.get.call_args.kwargs["params"]["q"] == 'title:"dark matter"'


# ── Zenodo ───────────────────────────────────────────────────────────────────


class TestZenodoFixes:
    def test_token_sent_as_header_not_param(self):
        from mosaic.sources.zenodo import ZenodoSource

        cls, mc = _client(get=_resp(json_data={"hits": {"hits": []}}))
        with patch("httpx.Client", cls):
            ZenodoSource(api_key="TOKEN").search("x")
        assert "access_token" not in mc.get.call_args.kwargs["params"]
        assert cls.call_args.kwargs["headers"] == {"Authorization": "Bearer TOKEN"}

    def test_restricted_record_not_open_access(self):
        from mosaic.sources.zenodo import ZenodoSource

        hit = {
            "metadata": {"title": "T", "access_right": "restricted"},
            "files": [{"key": "p.pdf", "links": {"self": "https://zenodo.org/p.pdf"}}],
        }
        paper = ZenodoSource()._parse(hit)
        assert paper.is_open_access is False
        assert paper.pdf_url is None

    def test_open_record_is_open_access(self):
        from mosaic.sources.zenodo import ZenodoSource

        hit = {"metadata": {"title": "T", "access_right": "open"}}
        assert ZenodoSource()._parse(hit).is_open_access is True


# ── OpenAlex ─────────────────────────────────────────────────────────────────


class TestOpenAlexFixes:
    def test_comma_removed_from_title_search_filter(self):
        from mosaic.sources.openalex import OpenAlexSource

        cls, mc = _client(get=_resp(json_data={"results": []}))
        with patch("httpx.Client", cls):
            OpenAlexSource().search(
                "graphene, oxide",
                filters=SearchFilters(field="title", year_from=2020, year_to=2021),
            )
        assert mc.get.call_args.kwargs["params"]["filter"] == (
            "title.search:graphene oxide,publication_year:2020-2021"
        )

    def test_null_author_names_dropped(self):
        from mosaic.sources.openalex import OpenAlexSource

        item = {
            "title": "T",
            "authorships": [
                {"author": {"display_name": None}},
                {"author": None},
                {"author": {"display_name": "A B"}},
            ],
            "doi": "https://doi.org/10.1/X",
        }
        paper = OpenAlexSource()._parse(item)
        assert paper.authors == ["A B"]
        assert paper.doi == "10.1/X"


# ── IEEE ─────────────────────────────────────────────────────────────────────


class TestIeeeNativeFilters:
    def _params(self, **kw):
        from mosaic.sources.ieee import IEEEXploreSource

        cls, mc = _client(get=_resp(json_data={"articles": []}))
        with patch("httpx.Client", cls):
            IEEEXploreSource(api_key="k").search("x", filters=SearchFilters(**kw))
        return mc.get.call_args.kwargs["params"]

    def test_single_author_and_journal_native(self):
        params = self._params(authors=["Hinton"], journal="TPAMI")
        assert params["author"] == "Hinton"
        assert params["publication_title"] == "TPAMI"

    def test_multiple_authors_left_to_post_filter(self):
        assert "author" not in self._params(authors=["A", "B"])


# ── Custom source ────────────────────────────────────────────────────────────


class TestCustomSourceFixes:
    def test_null_author_names_dropped_and_doi_normalised(self):
        from mosaic.sources.custom import CustomSource

        src = CustomSource(
            {
                "name": "C",
                "url": "https://c.example/api",
                "fields": {"title": "t", "doi": "d"},
                "authors_path": "people",
                "authors_field": "name",
            }
        )
        paper = src._parse(
            {
                "t": "Title",
                "d": "https://doi.org/10.9/ABC",
                "people": [{"name": None}, {"name": "Ada"}, {}],
            }
        )
        assert paper.authors == ["Ada"]
        assert paper.doi == "10.9/ABC"


# ── Unpaywall ────────────────────────────────────────────────────────────────


class TestUnpaywallFixes:
    def test_doi_url_encoded_and_normalised(self):
        from mosaic.sources import unpaywall

        with patch("httpx.get", return_value=_resp(json_data={"is_oa": False})) as get:
            unpaywall.resolve("https://doi.org/10.1002/(SICI)1097#x", "me@x.org")
        url = get.call_args.args[0]
        assert url == "https://api.unpaywall.org/v2/10.1002/%28SICI%291097%23x"


# ── Browser sources: real failures surface as SourceError ────────────────────


def _raise_in_run(message):
    def _run(coro):
        coro.close()
        raise RuntimeError(message)

    return _run


class TestScienceDirectBrowserErrors:
    def _src(self):
        from mosaic.sources.sciencedirect_browser import ScienceDirectBrowserSource

        return ScienceDirectBrowserSource()

    def test_no_session_returns_empty(self):
        with patch("mosaic.auth.find_session_for_url", return_value=None):
            assert self._src().search("x") == []

    def test_browser_failure_raises(self):
        with (
            patch("mosaic.auth.find_session_for_url", return_value="elsevier"),
            patch("mosaic.sources.sciencedirect_browser.ensure_playwright"),
            patch(
                "mosaic.sources.sciencedirect_browser.asyncio.run",
                side_effect=_raise_in_run("net::ERR_TIMED_OUT"),
            ),
            pytest.raises(SourceError, match="ERR_TIMED_OUT"),
        ):
            self._src().search("x")

    def test_expired_session_error_passes_through(self):
        def _run(coro):
            coro.close()
            raise SourceError("session has expired — run: mosaic auth login elsevier")

        with (
            patch("mosaic.auth.find_session_for_url", return_value="elsevier"),
            patch("mosaic.sources.sciencedirect_browser.ensure_playwright"),
            patch("mosaic.sources.sciencedirect_browser.asyncio.run", side_effect=_run),
            pytest.raises(SourceError, match="mosaic auth login elsevier"),
        ):
            self._src().search("x")

    def test_missing_playwright_raises_source_error_not_system_exit(self):
        with (
            patch("mosaic.auth.find_session_for_url", return_value="elsevier"),
            patch.dict("sys.modules", {"playwright": None}),
            pytest.raises(SourceError, match="Playwright"),
        ):
            self._src().search("x")


class TestSpringerBrowserErrors:
    def _src(self):
        from mosaic.sources.springer_browser import SpringerBrowserSource

        return SpringerBrowserSource()

    def test_browser_failure_raises(self):
        with (
            patch("mosaic.sources.springer_browser.ensure_playwright"),
            patch(
                "mosaic.sources.springer_browser.asyncio.run",
                side_effect=_raise_in_run("Target closed"),
            ),
            pytest.raises(SourceError, match="Target closed"),
        ):
            self._src().search("x")

    def test_missing_playwright_raises_source_error(self):
        with (
            patch.dict("sys.modules", {"playwright": None}),
            pytest.raises(SourceError, match="Playwright"),
        ):
            self._src().search("x")

    def test_build_url_unchanged(self):
        url = self._src()._build_url("deep learning", SearchFilters(year_from=2020), 1)
        assert "query=deep+learning" in url
        assert "dateFrom=2020" in url


# ── Error paths: non-2xx responses propagate (and are redacted upstream) ─────


class TestHttpErrorsPropagate:
    @pytest.mark.parametrize(
        ("module", "cls_name", "kwargs"),
        [
            ("mosaic.sources.ieee", "IEEEXploreSource", {"api_key": "SECRET"}),
            ("mosaic.sources.springer_api", "SpringerAPISource", {"api_key": "SECRET"}),
            ("mosaic.sources.crossref", "CrossrefSource", {}),
            ("mosaic.sources.hal", "HALSource", {}),
            ("mosaic.sources.dblp", "DBLPSource", {}),
        ],
    )
    def test_http_error_raised_and_redacted_by_search_all(self, module, cls_name, kwargs):
        import importlib

        from mosaic.search import search_all

        source = getattr(importlib.import_module(module), cls_name)(**kwargs)
        cls, _mc = _client(get=_resp(status=403))
        errors: list[str] = []
        with patch("httpx.Client", cls):
            assert search_all([source], "x", errors=errors, parallel=False) == []
        assert len(errors) == 1
        assert "403" in errors[0]
        assert "SECRET" not in errors[0]
