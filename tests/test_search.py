"""Tests for fan-out search, deduplication, and filtering."""
from unittest.mock import MagicMock
from mosaic.models import Paper, SearchFilters
from mosaic.search import search_all
from mosaic.sources.base import BaseSource


def _make_source(name: str, results: list[Paper], available: bool = True) -> BaseSource:
    src = MagicMock(spec=BaseSource)
    src.name = name
    src.available.return_value = available
    src.search.return_value = results
    return src


def _paper(doi="10.1/test", title="Paper", year=2020, abstract=None, pdf_url=None, citation_count=None):
    return Paper(title=title, doi=doi, year=year, abstract=abstract, pdf_url=pdf_url, authors=["A"],
                 citation_count=citation_count)


class TestDeduplication:
    def test_same_doi_from_two_sources_yields_one_result(self):
        p1 = _paper(doi="10.1/x", title="T")
        p2 = _paper(doi="10.1/x", title="T")
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert len(results) == 1

    def test_different_dois_both_kept(self):
        src = _make_source("A", [_paper(doi="10.1/x"), _paper(doi="10.1/y")])
        results = search_all([src], "q")
        assert len(results) == 2


class TestMerging:
    def test_abstract_filled_from_second_source(self):
        p1 = _paper(doi="10.1/x", abstract=None)
        p2 = _paper(doi="10.1/x", abstract="Rich abstract")
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert results[0].abstract == "Rich abstract"

    def test_pdf_url_filled_from_second_source(self):
        p1 = _paper(doi="10.1/x", pdf_url=None)
        p2 = _paper(doi="10.1/x", pdf_url="https://example.com/paper.pdf")
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert results[0].pdf_url == "https://example.com/paper.pdf"

    def test_existing_abstract_not_overwritten(self):
        p1 = _paper(doi="10.1/x", abstract="Original")
        p2 = _paper(doi="10.1/x", abstract="Should not overwrite")
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert results[0].abstract == "Original"


class TestErrorHandling:
    def test_failing_source_captured_in_errors(self):
        src = _make_source("Bad", [])
        src.search.side_effect = RuntimeError("timeout")
        errors = []
        results = search_all([src], "q", errors=errors)
        assert results == []
        assert len(errors) == 1
        assert "Bad" in errors[0]

    def test_failing_source_does_not_prevent_other_sources(self):
        bad = _make_source("Bad", [])
        bad.search.side_effect = RuntimeError("timeout")
        good = _make_source("Good", [_paper()])
        results = search_all([bad, good], "q")
        assert len(results) == 1

    def test_unavailable_source_skipped(self):
        src = _make_source("Unavail", [], available=False)
        results = search_all([src], "q")
        src.search.assert_not_called()
        assert results == []


class TestCitationMerging:
    def test_citation_count_filled_from_second_source(self):
        p1 = _paper(doi="10.1/x", citation_count=None)
        p2 = _paper(doi="10.1/x", citation_count=42)
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert results[0].citation_count == 42

    def test_higher_citation_count_preferred(self):
        p1 = _paper(doi="10.1/x", citation_count=10)
        p2 = _paper(doi="10.1/x", citation_count=99)
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert results[0].citation_count == 99

    def test_existing_citation_count_not_lowered(self):
        p1 = _paper(doi="10.1/x", citation_count=100)
        p2 = _paper(doi="10.1/x", citation_count=5)
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert results[0].citation_count == 100

    def test_none_does_not_overwrite_existing(self):
        p1 = _paper(doi="10.1/x", citation_count=50)
        p2 = _paper(doi="10.1/x", citation_count=None)
        src_a = _make_source("A", [p1])
        src_b = _make_source("B", [p2])
        results = search_all([src_a, src_b], "q")
        assert results[0].citation_count == 50


class TestSortByCitations:
    def test_sort_by_citations_descending(self):
        papers = [
            _paper(doi="10.1/a", citation_count=5),
            _paper(doi="10.1/b", citation_count=100),
            _paper(doi="10.1/c", citation_count=20),
        ]
        src = _make_source("A", papers)
        results = search_all([src], "q")
        results.sort(key=lambda p: p.citation_count or 0, reverse=True)
        assert [p.citation_count for p in results] == [100, 20, 5]

    def test_sort_by_citations_none_last(self):
        papers = [
            _paper(doi="10.1/a", citation_count=None),
            _paper(doi="10.1/b", citation_count=50),
            _paper(doi="10.1/c", citation_count=None),
        ]
        src = _make_source("A", papers)
        results = search_all([src], "q")
        results.sort(key=lambda p: p.citation_count or 0, reverse=True)
        assert results[0].citation_count == 50
        assert results[1].citation_count is None
        assert results[2].citation_count is None


class TestPostProcessingFilter:
    def test_year_filter_removes_out_of_range(self):
        papers = [_paper(doi=f"10.1/{i}", year=y) for i, y in enumerate([2018, 2020, 2023])]
        src = _make_source("A", papers)
        f = SearchFilters(year_from=2019, year_to=2022)
        results = search_all([src], "q", filters=f)
        assert len(results) == 1
        assert results[0].year == 2020

    def test_filters_passed_to_source(self):
        src = _make_source("A", [])
        f = SearchFilters(year_from=2020)
        search_all([src], "query", filters=f)
        src.search.assert_called_once_with("query", max_results=25, filters=f)


class TestSearchStats:
    def test_stats_populated_per_source(self):
        src_a = _make_source("A", [_paper(doi="10.1/a"), _paper(doi="10.1/b")])
        src_b = _make_source("B", [_paper(doi="10.1/c")])
        stats = {}
        search_all([src_a, src_b], "q", stats=stats)
        assert stats["per_source"] == {"A": 2, "B": 1}

    def test_stats_raw_total(self):
        src_a = _make_source("A", [_paper(doi="10.1/a"), _paper(doi="10.1/b")])
        src_b = _make_source("B", [_paper(doi="10.1/c"), _paper(doi="10.1/d")])
        stats = {}
        search_all([src_a, src_b], "q", stats=stats)
        assert stats["raw_total"] == 4

    def test_stats_merged_count(self):
        # Same DOI from two sources → 1 merged
        p1 = _paper(doi="10.1/x")
        p2 = _paper(doi="10.1/x")
        src_a = _make_source("A", [p1, _paper(doi="10.1/y")])
        src_b = _make_source("B", [p2])
        stats = {}
        search_all([src_a, src_b], "q", stats=stats)
        assert stats["merged"] == 1
        assert stats["unique"] == 2

    def test_stats_no_merges(self):
        src = _make_source("A", [_paper(doi="10.1/a"), _paper(doi="10.1/b")])
        stats = {}
        search_all([src], "q", stats=stats)
        assert stats["merged"] == 0
        assert stats["unique"] == 2

    def test_stats_after_filters(self):
        papers = [_paper(doi=f"10.1/{i}", year=y) for i, y in enumerate([2018, 2020, 2023])]
        src = _make_source("A", papers)
        stats = {}
        f = SearchFilters(year_from=2019, year_to=2022)
        search_all([src], "q", filters=f, stats=stats)
        assert stats["unique"] == 3       # before post-filter
        assert stats["after_filters"] == 1

    def test_stats_not_populated_when_none(self):
        src = _make_source("A", [_paper()])
        # should not raise; stats param absent
        results = search_all([src], "q")
        assert len(results) == 1

    def test_stats_empty_when_no_sources(self):
        stats = {}
        search_all([], "q", stats=stats)
        assert stats["raw_total"] == 0
        assert stats["unique"] == 0
        assert stats["merged"] == 0
