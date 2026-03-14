"""Tests for mosaic/services.py, mosaic/errors.py, mosaic/ui/jobs.py, and mosaic/parsing.py."""

import threading
import time

from mosaic.errors import ConfigError, DownloadError, MosaicError, SourceError
from mosaic.models import Paper
from mosaic.parsing import (
    extract_first,
    normalise_doi,
    parse_authors_given_family,
    parse_authors_name_key,
    parse_year,
    parse_year_earliest,
    split_authors,
    strip_html,
)
from mosaic.services import build_filters, filter_papers, merge_papers
from mosaic.ui.jobs import JobManager

# ── services.build_filters ───────────────────────────────────────────────────


class TestBuildFilters:
    def test_build_filters_empty(self):
        """No args returns (None, None)."""
        filters, warning = build_filters()
        assert filters is None
        assert warning is None

    def test_build_filters_year_single(self):
        """'2020' parses to exact year."""
        filters, warning = build_filters(year="2020")
        assert warning is None
        assert filters is not None
        assert filters.year_from == 2020
        assert filters.year_to == 2020
        assert filters.years is None

    def test_build_filters_year_range(self):
        """'2020-2024' parses to inclusive range."""
        filters, warning = build_filters(year="2020-2024")
        assert warning is None
        assert filters is not None
        assert filters.year_from == 2020
        assert filters.year_to == 2024

    def test_build_filters_year_list(self):
        """'2020,2022,2024' parses to explicit year list."""
        filters, warning = build_filters(year="2020,2022,2024")
        assert warning is None
        assert filters is not None
        assert filters.years == [2020, 2022, 2024]

    def test_build_filters_year_invalid(self):
        """'abc' returns (filters, warning)."""
        filters, warning = build_filters(year="abc", author="Smith")
        assert warning is not None
        assert "Invalid year" in warning
        # Other fields should still be applied
        assert filters is not None
        assert filters.authors == ["Smith"]

    def test_build_filters_author_string(self):
        """'Smith' produces authors list."""
        filters, warning = build_filters(author="Smith")
        assert warning is None
        assert filters is not None
        assert filters.authors == ["Smith"]

    def test_build_filters_author_list(self):
        """["Smith", "Jones"] works directly."""
        filters, warning = build_filters(author=["Smith", "Jones"])
        assert warning is None
        assert filters is not None
        assert filters.authors == ["Smith", "Jones"]

    def test_build_filters_journal(self):
        """Journal is set on filters."""
        filters, warning = build_filters(journal="Nature")
        assert warning is None
        assert filters is not None
        assert filters.journal == "Nature"

    def test_build_filters_field(self):
        """Field is set on filters."""
        filters, warning = build_filters(field="title")
        assert warning is None
        assert filters is not None
        assert filters.field == "title"

    def test_build_filters_raw_query(self):
        """raw_query is set on filters."""
        filters, warning = build_filters(raw_query="TI=transformer")
        assert warning is None
        assert filters is not None
        assert filters.raw_query == "TI=transformer"


# ── services.filter_papers ───────────────────────────────────────────────────


class TestFilterPapers:
    def _papers(self):
        return [
            Paper(
                title="A", is_open_access=True, pdf_url="http://a.pdf", citation_count=10, year=2020
            ),
            Paper(title="B", is_open_access=False, pdf_url=None, citation_count=50, year=2022),
            Paper(title="C", is_open_access=True, pdf_url=None, citation_count=5, year=2021),
            Paper(
                title="D",
                is_open_access=False,
                pdf_url="http://d.pdf",
                citation_count=None,
                year=None,
            ),
        ]

    def test_filter_papers_oa_only(self):
        """Filters to OA papers (or those with a PDF URL)."""
        result = filter_papers(self._papers(), oa_only=True)
        # A (OA+PDF), C (OA), D (has PDF) should pass
        titles = [p.title for p in result]
        assert "A" in titles
        assert "C" in titles
        assert "D" in titles
        assert "B" not in titles

    def test_filter_papers_pdf_only(self):
        """Filters to papers with PDF URL."""
        result = filter_papers(self._papers(), pdf_only=True)
        titles = [p.title for p in result]
        assert titles == ["A", "D"]

    def test_filter_papers_sort_citations(self):
        """Sorts by citations descending."""
        result = filter_papers(self._papers(), sort_by="citations")
        citations = [p.citation_count or 0 for p in result]
        assert citations == [50, 10, 5, 0]

    def test_filter_papers_sort_year(self):
        """Sorts by year descending."""
        result = filter_papers(self._papers(), sort_by="year")
        years = [p.year or 0 for p in result]
        assert years == [2022, 2021, 2020, 0]

    def test_filter_papers_no_mutation(self):
        """Original list is not mutated."""
        original = self._papers()
        original_titles = [p.title for p in original]
        filter_papers(original, pdf_only=True, sort_by="citations")
        assert [p.title for p in original] == original_titles


# ── services.merge_papers ────────────────────────────────────────────────────


class TestMergePapers:
    def test_merge_papers_new(self):
        """New paper is added to seen dict."""
        seen: dict[str, Paper] = {}
        p = Paper(title="New Paper", doi="10.1234/new")
        merge_papers(seen, p)
        assert "doi:10.1234/new" in seen
        assert seen["doi:10.1234/new"] is p

    def test_merge_papers_duplicate(self):
        """Existing paper gets enriched with missing fields."""
        existing = Paper(title="Paper", doi="10.1234/test", abstract=None, pdf_url=None)
        seen = {existing.uid: existing}
        incoming = Paper(
            title="Paper",
            doi="10.1234/test",
            abstract="An abstract.",
            pdf_url="http://example.com/paper.pdf",
        )
        merge_papers(seen, incoming)
        assert existing.abstract == "An abstract."
        assert existing.pdf_url == "http://example.com/paper.pdf"

    def test_merge_papers_citation_update(self):
        """Higher citation count wins."""
        existing = Paper(title="Paper", doi="10.1234/test", citation_count=5)
        seen = {existing.uid: existing}
        incoming = Paper(title="Paper", doi="10.1234/test", citation_count=20)
        merge_papers(seen, incoming)
        assert existing.citation_count == 20

    def test_merge_papers_lower_citations_ignored(self):
        """Lower citation count does not overwrite."""
        existing = Paper(title="Paper", doi="10.1234/test", citation_count=20)
        seen = {existing.uid: existing}
        incoming = Paper(title="Paper", doi="10.1234/test", citation_count=5)
        merge_papers(seen, incoming)
        assert existing.citation_count == 20

    def test_merge_papers_none_citation_to_some(self):
        """None citation on existing is updated when incoming has a value."""
        existing = Paper(title="Paper", doi="10.1234/test", citation_count=None)
        seen = {existing.uid: existing}
        incoming = Paper(title="Paper", doi="10.1234/test", citation_count=10)
        merge_papers(seen, incoming)
        assert existing.citation_count == 10

    def test_merge_papers_does_not_overwrite_existing_fields(self):
        """Existing non-empty fields are not overwritten."""
        existing = Paper(
            title="Paper",
            doi="10.1234/test",
            abstract="Original abstract",
            pdf_url="http://original.pdf",
        )
        seen = {existing.uid: existing}
        incoming = Paper(
            title="Paper",
            doi="10.1234/test",
            abstract="New abstract",
            pdf_url="http://new.pdf",
        )
        merge_papers(seen, incoming)
        assert existing.abstract == "Original abstract"
        assert existing.pdf_url == "http://original.pdf"


# ── errors ───────────────────────────────────────────────────────────────────


class TestErrors:
    def test_mosaic_error_hierarchy(self):
        """MosaicError is an Exception subclass."""
        assert issubclass(MosaicError, Exception)
        err = MosaicError("test")
        assert isinstance(err, Exception)

    def test_source_error(self):
        """SourceError is a MosaicError subclass."""
        assert issubclass(SourceError, MosaicError)
        err = SourceError("source failed")
        assert isinstance(err, MosaicError)
        assert isinstance(err, Exception)

    def test_download_error(self):
        """DownloadError is a MosaicError subclass."""
        assert issubclass(DownloadError, MosaicError)
        err = DownloadError("download failed")
        assert isinstance(err, MosaicError)

    def test_config_error(self):
        """ConfigError is a MosaicError subclass."""
        assert issubclass(ConfigError, MosaicError)
        err = ConfigError("bad config")
        assert isinstance(err, MosaicError)

    def test_error_messages(self):
        """Errors carry message strings."""
        assert str(MosaicError("base msg")) == "base msg"
        assert str(SourceError("src msg")) == "src msg"
        assert str(DownloadError("dl msg")) == "dl msg"
        assert str(ConfigError("cfg msg")) == "cfg msg"


# ── ui.jobs ──────────────────────────────────────────────────────────────────


class TestJobs:
    def test_submit_returns_job_id(self):
        """submit returns a string ID."""
        mgr = JobManager(max_workers=2)
        try:
            job_id = mgr.submit(lambda: 42)
            assert isinstance(job_id, str)
            assert len(job_id) == 12
        finally:
            mgr.shutdown()

    def test_job_completes_successfully(self):
        """Job status becomes 'done' after successful completion."""
        mgr = JobManager(max_workers=2)
        try:
            job_id = mgr.submit(lambda: "result_value")
            job = mgr.get(job_id)
            assert job is not None
            job.wait(timeout=5)
            assert job.status == "done"
            assert job.result == "result_value"
        finally:
            mgr.shutdown()

    def test_job_captures_error(self):
        """Exception leads to job.status 'error' + error_message."""

        def failing_fn():
            raise RuntimeError("something broke")

        mgr = JobManager(max_workers=2)
        try:
            job_id = mgr.submit(failing_fn)
            job = mgr.get(job_id)
            assert job is not None
            job.wait(timeout=5)
            assert job.status == "error"
            assert "something broke" in job.error_message
        finally:
            mgr.shutdown()

    def test_job_wait(self):
        """job.wait() blocks until done."""
        mgr = JobManager(max_workers=2)
        try:
            job_id = mgr.submit(lambda: time.sleep(0.1) or "waited")
            job = mgr.get(job_id)
            assert job is not None
            done = job.wait(timeout=5)
            assert done is True
            assert job.status == "done"
            assert job.result == "waited"
        finally:
            mgr.shutdown()

    def test_get_nonexistent(self):
        """get returns None for unknown ID."""
        mgr = JobManager(max_workers=2)
        try:
            assert mgr.get("does_not_exist") is None
        finally:
            mgr.shutdown()

    def test_pop_removes_job(self):
        """pop removes and returns job."""
        mgr = JobManager(max_workers=2)
        try:
            job_id = mgr.submit(lambda: 1)
            job = mgr.get(job_id)
            assert job is not None
            job.wait(timeout=5)
            popped = mgr.pop(job_id)
            assert popped is not None
            assert popped.id == job_id
            # After pop, get should return None
            assert mgr.get(job_id) is None
        finally:
            mgr.shutdown()

    def test_stale_job_cleanup(self):
        """Old completed jobs are cleaned up."""
        mgr = JobManager(max_workers=2)
        try:
            job_id = mgr.submit(lambda: "done")
            job = mgr.get(job_id)
            assert job is not None
            job.wait(timeout=5)
            # Manually set created_at far in the past to simulate staleness
            job.created_at = time.monotonic() - 2000
            stale = mgr.stale_job_ids()
            assert job_id in stale
            # Submitting a new job triggers cleanup
            mgr.submit(lambda: "trigger_cleanup")
            # The stale job should now be cleaned up
            assert mgr.get(job_id) is None
        finally:
            mgr.shutdown()

    def test_concurrent_submissions(self):
        """Multiple jobs run in parallel."""
        mgr = JobManager(max_workers=4)
        try:
            results = []
            lock = threading.Lock()

            def work(n):
                with lock:
                    results.append(n)
                return n

            ids = [mgr.submit(work, i) for i in range(4)]
            for jid in ids:
                job = mgr.get(jid)
                assert job is not None
                job.wait(timeout=5)
                assert job.status == "done"
            assert sorted(results) == [0, 1, 2, 3]
        finally:
            mgr.shutdown()

    def test_job_wait_timeout(self):
        """job.wait() returns False on timeout."""
        mgr = JobManager(max_workers=1)
        try:
            event = threading.Event()
            job_id = mgr.submit(lambda: event.wait(5))
            job = mgr.get(job_id)
            assert job is not None
            done = job.wait(timeout=0.05)
            assert done is False
            # Let the job finish to avoid thread leak
            event.set()
            job.wait(timeout=5)
        finally:
            mgr.shutdown()

    def test_pop_nonexistent(self):
        """pop returns None for unknown ID."""
        mgr = JobManager(max_workers=1)
        try:
            assert mgr.pop("nope") is None
        finally:
            mgr.shutdown()


# ── parsing ──────────────────────────────────────────────────────────────────


class TestParseYear:
    def test_parse_year_int(self):
        """parse_year(2020) returns 2020."""
        assert parse_year(2020) == 2020

    def test_parse_year_string(self):
        """parse_year('2020') returns 2020."""
        assert parse_year("2020") == 2020

    def test_parse_year_date_string(self):
        """parse_year('2020-03-15') returns 2020."""
        assert parse_year("2020-03-15") == 2020

    def test_parse_year_none(self):
        """parse_year(None) returns None."""
        assert parse_year(None) is None

    def test_parse_year_empty(self):
        """parse_year('') returns None."""
        assert parse_year("") is None

    def test_parse_year_invalid(self):
        """parse_year('abc') returns None."""
        assert parse_year("abc") is None

    def test_parse_year_whitespace(self):
        """parse_year with surrounding whitespace still works."""
        assert parse_year("  2020  ") == 2020


class TestParseYearEarliest:
    def test_parse_year_earliest(self):
        """Picks the earliest year from multiple fields."""
        item = {"epubdate": "2020", "pubdate": "2021"}
        assert parse_year_earliest(item, ["epubdate", "pubdate"]) == 2020

    def test_parse_year_earliest_missing_fields(self):
        """Skips missing/empty fields gracefully."""
        item = {"epubdate": "", "pubdate": "2021"}
        assert parse_year_earliest(item, ["epubdate", "pubdate"]) == 2021

    def test_parse_year_earliest_all_missing(self):
        """Returns None when no fields have valid years."""
        item = {"epubdate": "", "pubdate": ""}
        assert parse_year_earliest(item, ["epubdate", "pubdate"]) is None


class TestExtractFirst:
    def test_extract_first_list(self):
        """First element from list."""
        assert extract_first(["hello", "world"]) == "hello"

    def test_extract_first_string(self):
        """String passes through."""
        assert extract_first("hello") == "hello"

    def test_extract_first_none(self):
        """None returns None."""
        assert extract_first(None) is None

    def test_extract_first_empty_list(self):
        """Empty list returns None."""
        assert extract_first([]) is None


class TestStripHtml:
    def test_strip_html(self):
        """Removes HTML tags and collapses whitespace."""
        assert strip_html("<jats:p>Hello <b>world</b></jats:p>") == "Hello world"

    def test_strip_html_none(self):
        """None returns None."""
        assert strip_html(None) is None

    def test_strip_html_empty(self):
        """Empty string returns None."""
        assert strip_html("") is None

    def test_strip_html_plain_text(self):
        """Plain text passes through."""
        assert strip_html("Hello world") == "Hello world"


class TestNormaliseDoi:
    def test_normalise_doi(self):
        """Strips https://doi.org/ prefix."""
        assert normalise_doi("https://doi.org/10.1234/foo") == "10.1234/foo"

    def test_normalise_doi_bare(self):
        """Bare DOI passes through."""
        assert normalise_doi("10.1234/foo") == "10.1234/foo"

    def test_normalise_doi_http(self):
        """Strips http://doi.org/ prefix."""
        assert normalise_doi("http://doi.org/10.1234/foo") == "10.1234/foo"

    def test_normalise_doi_dx(self):
        """Strips https://dx.doi.org/ prefix."""
        assert normalise_doi("https://dx.doi.org/10.1234/foo") == "10.1234/foo"

    def test_normalise_doi_none(self):
        """None returns None."""
        assert normalise_doi(None) is None

    def test_normalise_doi_empty(self):
        """Empty string returns None."""
        assert normalise_doi("") is None


class TestParseAuthorsNameKey:
    def test_parse_authors_name_key(self):
        """Extracts names from list of dicts."""
        items = [{"name": "Alice"}, {"name": "Bob"}]
        assert parse_authors_name_key(items) == ["Alice", "Bob"]

    def test_parse_authors_name_key_custom_key(self):
        """Works with a custom key."""
        items = [{"author": "Alice"}, {"author": "Bob"}]
        assert parse_authors_name_key(items, key="author") == ["Alice", "Bob"]

    def test_parse_authors_name_key_missing(self):
        """Skips entries where key is missing or empty."""
        items = [{"name": "Alice"}, {"other": "Bob"}, {"name": ""}]
        assert parse_authors_name_key(items) == ["Alice"]


class TestParseAuthorsGivenFamily:
    def test_parse_authors_given_family(self):
        """Crossref format: {given, family} produces 'Family, Given'."""
        items = [{"family": "Smith", "given": "John"}]
        assert parse_authors_given_family(items) == ["Smith, John"]

    def test_parse_authors_family_only(self):
        """Family-only entry."""
        items = [{"family": "Smith"}]
        assert parse_authors_given_family(items) == ["Smith"]

    def test_parse_authors_given_only(self):
        """Given-only entry."""
        items = [{"given": "John"}]
        assert parse_authors_given_family(items) == ["John"]

    def test_parse_authors_multiple(self):
        """Multiple authors."""
        items = [
            {"family": "Smith", "given": "John"},
            {"family": "Doe", "given": "Jane"},
        ]
        assert parse_authors_given_family(items) == ["Smith, John", "Doe, Jane"]


class TestSplitAuthors:
    def test_split_authors_comma(self):
        """Comma split."""
        assert split_authors("Smith, J, Doe, K", sep=",") == ["Smith", "J", "Doe", "K"]

    def test_split_authors_semicolon(self):
        """Semicolon split."""
        assert split_authors("Smith; Doe", sep=";") == ["Smith", "Doe"]

    def test_split_authors_empty(self):
        """Empty string returns empty list."""
        assert split_authors("") == []

    def test_split_authors_strips_whitespace(self):
        """Surrounding whitespace is stripped."""
        assert split_authors("  Alice  ,  Bob  ", sep=",") == ["Alice", "Bob"]
