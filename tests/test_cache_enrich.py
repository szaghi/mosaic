"""Phase 3 — smart upsert enrichment rules."""

from mosaic.models import Paper


def _p(**kw):
    defaults = {
        "title": "Test Paper",
        "doi": "10.1/test",
        "authors": ["Alice"],
        "year": 2020,
        "source": "arXiv",
    }
    defaults.update(kw)
    return Paper(**defaults)


class TestAbstractEnrichment:
    def test_keeps_longer_abstract(self, tmp_cache):
        tmp_cache.save(_p(abstract="Short."))
        tmp_cache.save(_p(abstract="Much longer abstract with more detail."))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.abstract == "Much longer abstract with more detail."

    def test_does_not_overwrite_with_shorter(self, tmp_cache):
        tmp_cache.save(_p(abstract="Much longer abstract with more detail."))
        tmp_cache.save(_p(abstract="Short."))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.abstract == "Much longer abstract with more detail."

    def test_fills_empty_abstract(self, tmp_cache):
        tmp_cache.save(_p(abstract=None))
        tmp_cache.save(_p(abstract="Now has one."))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.abstract == "Now has one."

    def test_does_not_overwrite_with_none(self, tmp_cache):
        tmp_cache.save(_p(abstract="Keep me."))
        tmp_cache.save(_p(abstract=None))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.abstract == "Keep me."


class TestPdfUrlEnrichment:
    def test_preserves_existing_pdf_url(self, tmp_cache):
        tmp_cache.save(_p(pdf_url="https://first.com/a.pdf"))
        tmp_cache.save(_p(pdf_url="https://second.com/b.pdf"))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.pdf_url == "https://first.com/a.pdf"

    def test_fills_missing_pdf_url(self, tmp_cache):
        tmp_cache.save(_p(pdf_url=None))
        tmp_cache.save(_p(pdf_url="https://example.com/a.pdf"))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.pdf_url == "https://example.com/a.pdf"

    def test_does_not_overwrite_with_none(self, tmp_cache):
        tmp_cache.save(_p(pdf_url="https://example.com/a.pdf"))
        tmp_cache.save(_p(pdf_url=None))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.pdf_url == "https://example.com/a.pdf"


class TestOpenAccessEnrichment:
    def test_true_supersedes_false(self, tmp_cache):
        tmp_cache.save(_p(is_open_access=False))
        tmp_cache.save(_p(is_open_access=True))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.is_open_access is True

    def test_false_does_not_overwrite_true(self, tmp_cache):
        tmp_cache.save(_p(is_open_access=True))
        tmp_cache.save(_p(is_open_access=False))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.is_open_access is True


class TestCitationCountEnrichment:
    def test_keeps_higher_citation_count(self, tmp_cache):
        tmp_cache.save(_p(citation_count=10))
        tmp_cache.save(_p(citation_count=50))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.citation_count == 50

    def test_does_not_overwrite_with_lower(self, tmp_cache):
        tmp_cache.save(_p(citation_count=50))
        tmp_cache.save(_p(citation_count=10))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.citation_count == 50

    def test_fills_missing_citation_count(self, tmp_cache):
        tmp_cache.save(_p(citation_count=None))
        tmp_cache.save(_p(citation_count=42))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.citation_count == 42

    def test_does_not_overwrite_with_none(self, tmp_cache):
        tmp_cache.save(_p(citation_count=42))
        tmp_cache.save(_p(citation_count=None))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.citation_count == 42


class TestAuthorsEnrichment:
    def test_keeps_longer_author_list(self, tmp_cache):
        tmp_cache.save(_p(authors=["Alice"]))
        tmp_cache.save(_p(authors=["Alice", "Bob", "Carol"]))
        p = tmp_cache.get_by_uid(_p().uid)
        assert len(p.authors) == 3

    def test_does_not_overwrite_with_shorter(self, tmp_cache):
        tmp_cache.save(_p(authors=["Alice", "Bob", "Carol"]))
        tmp_cache.save(_p(authors=["Alice"]))
        p = tmp_cache.get_by_uid(_p().uid)
        assert len(p.authors) == 3


class TestMetadataFillIfEmpty:
    def test_fills_journal_if_empty(self, tmp_cache):
        tmp_cache.save(_p(journal=None))
        tmp_cache.save(_p(journal="Nature"))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.journal == "Nature"

    def test_does_not_overwrite_journal(self, tmp_cache):
        tmp_cache.save(_p(journal="Science"))
        tmp_cache.save(_p(journal="Nature"))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.journal == "Science"

    def test_fills_url_if_empty(self, tmp_cache):
        tmp_cache.save(_p(url=None))
        tmp_cache.save(_p(url="https://example.com"))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.url == "https://example.com"

    def test_fills_arxiv_doi_if_empty(self, tmp_cache):
        # arxiv DOIs normalise to arxiv: UID — so both records share the same UID
        # and the doi column can be filled in from the second record.
        p1 = Paper(
            title="ArXiv Paper", authors=["Alice"], year=2020, arxiv_id="1234.56789", source="arXiv"
        )
        p2 = Paper(
            title="ArXiv Paper",
            authors=["Alice"],
            year=2020,
            doi="10.48550/arxiv.1234.56789",
            source="OpenAlex",
        )
        assert p1.uid == p2.uid  # both resolve to arxiv:1234.56789
        tmp_cache.save(p1)
        tmp_cache.save(p2)
        result = tmp_cache.get_by_uid(p1.uid)
        assert result.doi == "10.48550/arxiv.1234.56789"


class TestYearAndTitlePreserved:
    def test_year_not_overwritten(self, tmp_cache):
        tmp_cache.save(_p(year=2020))
        tmp_cache.save(_p(year=2021))
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.year == 2020

    def test_title_not_overwritten(self, tmp_cache):
        tmp_cache.save(_p(title="Original Title"))
        # Same DOI → same UID; different title
        p2 = Paper(
            title="Different Title", doi="10.1/test", authors=["Alice"], year=2020, source="arXiv"
        )
        tmp_cache.save(p2)
        p = tmp_cache.get_by_uid(_p().uid)
        assert p.title == "Original Title"
