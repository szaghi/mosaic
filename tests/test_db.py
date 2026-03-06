"""Tests for the SQLite cache layer."""
from mosaic.models import Paper
from mosaic.db import Cache


def _paper(doi="10.1/test", title="Test Paper", abstract=None, pdf_url=None):
    return Paper(
        title=title, doi=doi, authors=["Author A"], year=2020,
        abstract=abstract, pdf_url=pdf_url, source="arXiv", is_open_access=True,
    )


class TestUpsert:
    def test_save_and_retrieve_by_local_search(self, tmp_cache):
        p = _paper(title="Unique Title XYZ")
        tmp_cache.save(p)
        results = tmp_cache.search_local("Unique Title XYZ")
        assert len(results) == 1
        assert results[0].title == "Unique Title XYZ"

    def test_upsert_updates_pdf_url(self, tmp_cache):
        p = _paper(doi="10.1/x", pdf_url=None)
        tmp_cache.save(p)
        p2 = _paper(doi="10.1/x", pdf_url="https://example.com/a.pdf")
        tmp_cache.save(p2)
        results = tmp_cache.search_local("Test Paper")
        assert results[0].pdf_url == "https://example.com/a.pdf"

    def test_upsert_updates_abstract(self, tmp_cache):
        p = _paper(doi="10.1/x", abstract=None)
        tmp_cache.save(p)
        p2 = _paper(doi="10.1/x", abstract="New abstract")
        tmp_cache.save(p2)
        results = tmp_cache.search_local("Test Paper")
        assert results[0].abstract == "New abstract"

    def test_multiple_papers_stored(self, tmp_cache):
        for i in range(3):
            tmp_cache.save(_paper(doi=f"10.1/{i}", title=f"Paper {i}"))
        assert len(tmp_cache.search_local("Paper")) == 3


class TestDownloadTracking:
    def test_set_and_get_download(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, "/tmp/paper.pdf", "ok")
        rec = tmp_cache.get_download(paper.uid)
        assert rec is not None
        assert rec["status"] == "ok"
        assert rec["local_path"] == "/tmp/paper.pdf"

    def test_get_download_returns_none_for_unknown(self, tmp_cache):
        assert tmp_cache.get_download("nonexistent:uid") is None

    def test_set_download_updates_on_conflict(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, "/tmp/old.pdf", "ok")
        tmp_cache.set_download(paper.uid, "/tmp/new.pdf", "ok")
        rec = tmp_cache.get_download(paper.uid)
        assert rec["local_path"] == "/tmp/new.pdf"


class TestLocalSearch:
    def test_search_by_title_substring(self, tmp_cache):
        tmp_cache.save(_paper(title="Quantum Computing Advances"))
        tmp_cache.save(_paper(doi="10.1/b", title="Deep Learning Survey"))
        results = tmp_cache.search_local("Quantum")
        assert len(results) == 1
        assert "Quantum" in results[0].title

    def test_search_by_abstract(self, tmp_cache):
        tmp_cache.save(_paper(abstract="This paper discusses reinforcement learning."))
        results = tmp_cache.search_local("reinforcement")
        assert len(results) == 1

    def test_no_match_returns_empty(self, tmp_cache):
        tmp_cache.save(_paper(title="Something Else"))
        assert tmp_cache.search_local("QuantumComputing99") == []
