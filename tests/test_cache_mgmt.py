"""Phase 4 & 5 — cache management methods and richness predicate."""


from mosaic.models import Paper


def _p(doi="10.1/test", abstract=None, year=2020, authors=None, title="Test Paper", **kw):
    return Paper(
        title=title,
        doi=doi,
        authors=authors if authors is not None else ["Alice"],
        year=year,
        abstract=abstract,
        source="arXiv",
        **kw,
    )


# ── Phase 5: richness predicate ───────────────────────────────────────────────

class TestIsRich:
    def test_rich_paper(self, tmp_cache):
        tmp_cache.save(_p(abstract="Has an abstract."))
        assert tmp_cache.is_rich(_p().uid) is True

    def test_no_abstract_not_rich(self, tmp_cache):
        tmp_cache.save(_p(abstract=None))
        assert tmp_cache.is_rich(_p().uid) is False

    def test_no_authors_not_rich(self, tmp_cache):
        tmp_cache.save(_p(abstract="Has abstract.", authors=[]))
        assert tmp_cache.is_rich(_p(authors=[]).uid) is False

    def test_no_year_not_rich(self, tmp_cache):
        tmp_cache.save(_p(abstract="Has abstract.", year=None))
        assert tmp_cache.is_rich(_p(year=None).uid) is False

    def test_unknown_uid_not_rich(self, tmp_cache):
        assert tmp_cache.is_rich("doi:10.0/nonexistent") is False


class TestRichUids:
    def test_returns_rich_uids(self, tmp_cache):
        rich = _p(doi="10.1/rich", abstract="Has abstract.")
        poor = _p(doi="10.1/poor", abstract=None)
        tmp_cache.save(rich)
        tmp_cache.save(poor)
        uids = tmp_cache.rich_uids()
        assert rich.uid in uids
        assert poor.uid not in uids

    def test_empty_cache_returns_empty_set(self, tmp_cache):
        assert tmp_cache.rich_uids() == set()


# ── Phase 4: stats ────────────────────────────────────────────────────────────

class TestStats:
    def test_counts_papers(self, tmp_cache):
        for i in range(3):
            tmp_cache.save(_p(doi=f"10.1/{i}"))
        s = tmp_cache.stats()
        assert s["papers"] == 3

    def test_counts_open_access(self, tmp_cache):
        tmp_cache.save(_p(doi="10.1/oa", is_open_access=True))
        tmp_cache.save(_p(doi="10.1/closed", is_open_access=False))
        s = tmp_cache.stats()
        assert s["open_access"] == 1

    def test_counts_with_abstract(self, tmp_cache):
        tmp_cache.save(_p(doi="10.1/a", abstract="yes"))
        tmp_cache.save(_p(doi="10.1/b", abstract=None))
        s = tmp_cache.stats()
        assert s["with_abstract"] == 1

    def test_counts_downloads(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, "/tmp/x.pdf", "ok")
        s = tmp_cache.stats()
        assert s["downloaded"] == 1

    def test_db_bytes_positive(self, tmp_cache):
        tmp_cache.save(_p())
        assert tmp_cache.stats()["db_bytes"] > 0


# ── Phase 4: list_papers / count_papers ──────────────────────────────────────

class TestListPapers:
    def test_returns_all_papers(self, tmp_cache):
        for i in range(5):
            tmp_cache.save(_p(doi=f"10.1/{i}", title=f"Paper {i}"))
        assert len(tmp_cache.list_papers(limit=10)) == 5

    def test_limit_and_offset(self, tmp_cache):
        for i in range(10):
            tmp_cache.save(_p(doi=f"10.1/{i}"))
        page1 = tmp_cache.list_papers(limit=5, offset=0)
        page2 = tmp_cache.list_papers(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        uids1 = {p.uid for p in page1}
        uids2 = {p.uid for p in page2}
        assert uids1.isdisjoint(uids2)

    def test_query_filter(self, tmp_cache):
        tmp_cache.save(_p(doi="10.1/a", title="Quantum Computing"))
        tmp_cache.save(_p(doi="10.1/b", title="Deep Learning"))
        results = tmp_cache.list_papers(query="Quantum")
        assert len(results) == 1
        assert "Quantum" in results[0].title

    def test_count_papers_total(self, tmp_cache):
        for i in range(7):
            tmp_cache.save(_p(doi=f"10.1/{i}"))
        assert tmp_cache.count_papers() == 7

    def test_count_papers_with_query(self, tmp_cache):
        tmp_cache.save(_p(doi="10.1/a", title="Alpha paper"))
        tmp_cache.save(_p(doi="10.1/b", title="Beta paper"))
        assert tmp_cache.count_papers(query="Alpha") == 1


# ── Phase 4: verify + clean ───────────────────────────────────────────────────

class TestVerifyAndClean:
    def test_verify_existing_file(self, tmp_cache, tmp_path, paper):
        f = tmp_path / "paper.pdf"
        f.write_bytes(b"pdf")
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, str(f), "ok")
        results = tmp_cache.verify_downloads()
        assert results[0]["exists"] is True

    def test_verify_missing_file(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, "/nonexistent/path.pdf", "ok")
        results = tmp_cache.verify_downloads()
        assert results[0]["exists"] is False

    def test_clean_removes_missing(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, "/nonexistent/path.pdf", "ok")
        removed = tmp_cache.clean_stubs()
        assert removed == 1
        assert tmp_cache.get_download(paper.uid) is None

    def test_clean_keeps_existing(self, tmp_cache, tmp_path, paper):
        f = tmp_path / "paper.pdf"
        f.write_bytes(b"pdf")
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, str(f), "ok")
        removed = tmp_cache.clean_stubs()
        assert removed == 0
        assert tmp_cache.get_download(paper.uid) is not None


# ── Phase 4: clear ────────────────────────────────────────────────────────────

class TestClear:
    def test_clear_removes_all_papers(self, tmp_cache):
        for i in range(3):
            tmp_cache.save(_p(doi=f"10.1/{i}"))
        tmp_cache.clear()
        assert tmp_cache.stats()["papers"] == 0

    def test_clear_removes_downloads(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, "/tmp/x.pdf", "ok")
        tmp_cache.clear()
        assert tmp_cache.get_download(paper.uid) is None


# ── Phase 4: export tracking ─────────────────────────────────────────────────

class TestExportTracking:
    def test_track_and_check(self, tmp_cache, paper):
        tmp_cache.save(paper)
        assert tmp_cache.was_exported(paper.uid, "zotero") is False
        tmp_cache.track_export(paper.uid, "zotero")
        assert tmp_cache.was_exported(paper.uid, "zotero") is True

    def test_different_format_not_exported(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.track_export(paper.uid, "zotero")
        assert tmp_cache.was_exported(paper.uid, "obsidian") is False

    def test_different_destination_not_exported(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.track_export(paper.uid, "csv", "/tmp/a.csv")
        assert tmp_cache.was_exported(paper.uid, "csv", "/tmp/b.csv") is False

    def test_exports_count_in_stats(self, tmp_cache, paper):
        tmp_cache.save(paper)
        tmp_cache.track_export(paper.uid, "zotero")
        tmp_cache.track_export(paper.uid, "obsidian")
        assert tmp_cache.stats()["exports"] == 2
