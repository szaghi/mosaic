"""Tests for the mosaic/citations/ package."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mosaic.citations.crossref import CrossRefCitationProvider
from mosaic.citations.openalex import OpenAlexCitationProvider, _item_to_uid
from mosaic.citations.opencitations import OpenCitationsCitationProvider
from mosaic.citations.registry import build_citation_providers
from mosaic.db import Cache
from mosaic.models import Paper

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _paper(doi: str | None = None, arxiv_id: str | None = None, openalex_id: str | None = None) -> Paper:
    return Paper(
        title="Test Paper",
        doi=doi,
        arxiv_id=arxiv_id,
        openalex_id=openalex_id,
        source="test",
    )


def _mock_resp(json_data: dict | list, status_code: int = 200) -> MagicMock:
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data
    m.raise_for_status = MagicMock()
    return m


# ---------------------------------------------------------------------------
# _item_to_uid helper
# ---------------------------------------------------------------------------

class TestItemToUid:
    def test_regular_doi(self):
        item = {"doi": "https://doi.org/10.1234/foo"}
        assert _item_to_uid(item) == "doi:10.1234/foo"

    def test_doi_lowercased(self):
        item = {"doi": "https://doi.org/10.1234/FOO"}
        assert _item_to_uid(item) == "doi:10.1234/foo"

    def test_arxiv_doi_normalised(self):
        item = {"doi": "https://doi.org/10.48550/arxiv.2106.01234"}
        assert _item_to_uid(item) == "arxiv:2106.01234"

    def test_arxiv_from_ids(self):
        item = {"doi": None, "ids": {"arxiv": "https://arxiv.org/abs/2106.01234"}}
        assert _item_to_uid(item) == "arxiv:2106.01234"

    def test_no_identifiers(self):
        assert _item_to_uid({}) is None


# ---------------------------------------------------------------------------
# OpenAlexCitationProvider
# ---------------------------------------------------------------------------

class TestOpenAlexProvider:
    def test_can_handle_with_doi(self):
        p = _paper(doi="10.1234/foo")
        assert OpenAlexCitationProvider().can_handle(p)

    def test_can_handle_with_arxiv(self):
        p = _paper(arxiv_id="2106.01234")
        assert OpenAlexCitationProvider().can_handle(p)

    def test_can_handle_with_openalex_id(self):
        p = _paper(openalex_id="W123456")
        assert OpenAlexCitationProvider().can_handle(p)

    def test_cannot_handle_no_ids(self):
        p = Paper(title="No ID", source="test")
        assert not OpenAlexCitationProvider().can_handle(p)

    def test_fetch_references_by_doi(self):
        paper = _paper(doi="10.1234/foo")
        # First call: fetch referenced_works for the paper
        work_resp = _mock_resp({
            "id": "https://openalex.org/W111",
            "referenced_works": [
                "https://openalex.org/W222",
                "https://openalex.org/W333",
            ],
        })
        # Second call: batch resolve W-IDs → DOIs
        batch_resp = _mock_resp({
            "results": [
                {"doi": "https://doi.org/10.9999/a", "ids": {}},
                {"doi": "https://doi.org/10.9999/b", "ids": {}},
            ]
        })
        with patch("httpx.get", side_effect=[work_resp, batch_resp]):
            uids = OpenAlexCitationProvider().fetch_references(paper)
        assert uids == ["doi:10.9999/a", "doi:10.9999/b"]

    def test_fetch_references_by_arxiv(self):
        paper = _paper(arxiv_id="2106.01234")
        work_resp = _mock_resp({
            "referenced_works": ["https://openalex.org/W999"],
        })
        batch_resp = _mock_resp({
            "results": [{"doi": "https://doi.org/10.48550/arxiv.1901.00001", "ids": {}}]
        })
        with patch("httpx.get", side_effect=[work_resp, batch_resp]):
            uids = OpenAlexCitationProvider().fetch_references(paper)
        assert uids == ["arxiv:1901.00001"]

    def test_fetch_references_by_openalex_id(self):
        paper = _paper(openalex_id="W111")
        work_resp = _mock_resp({"referenced_works": ["https://openalex.org/W222"]})
        batch_resp = _mock_resp({"results": [{"doi": "https://doi.org/10.1111/x", "ids": {}}]})
        with patch("httpx.get", side_effect=[work_resp, batch_resp]) as mock_get:
            uids = OpenAlexCitationProvider().fetch_references(paper)
        # First call must use the W-ID URL directly, not a DOI/arXiv URL
        first_url = mock_get.call_args_list[0][0][0]
        assert first_url == "https://api.openalex.org/works/W111"
        assert uids == ["doi:10.1111/x"]

    def test_fetch_references_not_found(self):
        paper = _paper(doi="10.1234/missing")
        resp = _mock_resp({}, status_code=404)
        resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=resp):
            uids = OpenAlexCitationProvider().fetch_references(paper)
        assert uids == []

    def test_fetch_references_empty_referenced_works(self):
        paper = _paper(doi="10.1234/empty")
        work_resp = _mock_resp({"referenced_works": []})
        with patch("httpx.get", return_value=work_resp):
            uids = OpenAlexCitationProvider().fetch_references(paper)
        assert uids == []
        # Should not call the batch endpoint at all
        # (httpx.get called only once)

    def test_fetch_references_no_referenced_works_key(self):
        paper = _paper(doi="10.1234/nokey")
        work_resp = _mock_resp({"id": "https://openalex.org/W1"})
        with patch("httpx.get", return_value=work_resp):
            uids = OpenAlexCitationProvider().fetch_references(paper)
        assert uids == []

    def test_batch_chunking_triggers_multiple_calls(self):
        """More than 50 W-IDs should trigger multiple batch resolution calls."""
        from mosaic.citations.openalex import _BATCH_SIZE

        paper = _paper(doi="10.1234/big")
        n_refs = _BATCH_SIZE + 5
        w_ids = [f"https://openalex.org/W{i}" for i in range(n_refs)]
        work_resp = _mock_resp({"referenced_works": w_ids})
        # Each batch returns one result
        batch_resp = _mock_resp({"results": [{"doi": "https://doi.org/10.9/x", "ids": {}}]})

        with patch("httpx.get", side_effect=[work_resp, batch_resp, batch_resp]):
            with patch("time.sleep"):  # suppress delay
                uids = OpenAlexCitationProvider().fetch_references(paper)

        assert len(uids) == 2  # one result per batch call

    def test_network_error_returns_empty(self):
        paper = _paper(doi="10.1234/err")
        with patch("httpx.get", side_effect=Exception("timeout")):
            uids = OpenAlexCitationProvider().fetch_references(paper)
        assert uids == []

    def test_polite_pool_email_passed(self):
        paper = _paper(doi="10.1234/foo")
        work_resp = _mock_resp({"referenced_works": []})
        with patch("httpx.get", return_value=work_resp) as mock_get:
            OpenAlexCitationProvider(email="test@example.com").fetch_references(paper)
        params = mock_get.call_args_list[0][1]["params"]
        assert params.get("mailto") == "test@example.com"


# ---------------------------------------------------------------------------
# CrossRefCitationProvider
# ---------------------------------------------------------------------------

class TestCrossRefProvider:
    def test_can_handle_with_doi(self):
        p = _paper(doi="10.1234/foo")
        assert CrossRefCitationProvider().can_handle(p)

    def test_cannot_handle_no_doi(self):
        p = _paper(arxiv_id="2106.01234")
        assert not CrossRefCitationProvider().can_handle(p)

    def test_fetch_references_basic(self):
        paper = _paper(doi="10.1234/foo")
        resp = _mock_resp({
            "message": {
                "reference": [
                    {"DOI": "10.9999/ref1"},
                    {"DOI": "10.9999/ref2"},
                    {"unstructured": "Some citation without DOI"},
                ]
            }
        })
        with patch("httpx.get", return_value=resp):
            uids = CrossRefCitationProvider().fetch_references(paper)
        assert uids == ["doi:10.9999/ref1", "doi:10.9999/ref2"]

    def test_fetch_references_doi_lowercased(self):
        paper = _paper(doi="10.1234/foo")
        resp = _mock_resp({"message": {"reference": [{"DOI": "10.9999/REF"}]}})
        with patch("httpx.get", return_value=resp):
            uids = CrossRefCitationProvider().fetch_references(paper)
        assert uids == ["doi:10.9999/ref"]

    def test_fetch_references_missing_reference_field(self):
        paper = _paper(doi="10.1234/foo")
        resp = _mock_resp({"message": {}})
        with patch("httpx.get", return_value=resp):
            uids = CrossRefCitationProvider().fetch_references(paper)
        assert uids == []

    def test_fetch_references_not_found(self):
        paper = _paper(doi="10.1234/missing")
        resp = _mock_resp({}, status_code=404)
        resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=resp):
            uids = CrossRefCitationProvider().fetch_references(paper)
        assert uids == []

    def test_email_in_user_agent(self):
        paper = _paper(doi="10.1234/foo")
        resp = _mock_resp({"message": {"reference": []}})
        with patch("httpx.get", return_value=resp) as mock_get:
            CrossRefCitationProvider(email="me@example.com").fetch_references(paper)
        headers = mock_get.call_args_list[0][1]["headers"]
        assert "me@example.com" in headers.get("User-Agent", "")

    def test_network_error_returns_empty(self):
        paper = _paper(doi="10.1234/err")
        with patch("httpx.get", side_effect=Exception("timeout")):
            uids = CrossRefCitationProvider().fetch_references(paper)
        assert uids == []


# ---------------------------------------------------------------------------
# OpenCitationsCitationProvider
# ---------------------------------------------------------------------------

class TestOpenCitationsProvider:
    def test_can_handle_with_doi(self):
        p = _paper(doi="10.1234/foo")
        assert OpenCitationsCitationProvider().can_handle(p)

    def test_cannot_handle_no_doi(self):
        p = _paper(arxiv_id="2106.01234")
        assert not OpenCitationsCitationProvider().can_handle(p)

    def test_fetch_references_basic(self):
        paper = _paper(doi="10.1234/foo")
        resp = _mock_resp([
            {"cited": "doi:10.9999/a"},
            {"cited": "doi:10.9999/b"},
        ])
        with patch("httpx.get", return_value=resp):
            uids = OpenCitationsCitationProvider().fetch_references(paper)
        assert uids == ["doi:10.9999/a", "doi:10.9999/b"]

    def test_fetch_references_doi_prefix_stripped(self):
        paper = _paper(doi="10.1234/foo")
        resp = _mock_resp([{"cited": "doi:10.9999/FOO"}])
        with patch("httpx.get", return_value=resp):
            uids = OpenCitationsCitationProvider().fetch_references(paper)
        assert uids == ["doi:10.9999/foo"]

    def test_fetch_references_not_found(self):
        paper = _paper(doi="10.1234/missing")
        resp = _mock_resp([], status_code=404)
        resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=resp):
            uids = OpenCitationsCitationProvider().fetch_references(paper)
        assert uids == []

    def test_network_error_returns_empty(self):
        paper = _paper(doi="10.1234/err")
        with patch("httpx.get", side_effect=Exception("timeout")):
            uids = OpenCitationsCitationProvider().fetch_references(paper)
        assert uids == []


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_default_providers_returned(self):
        cfg = {"rag": {"citations": {}}}
        providers = build_citation_providers(cfg)
        names = [p.name for p in providers]
        assert "openalex" in names
        assert "crossref" in names

    def test_custom_provider_order(self):
        cfg = {"rag": {"citations": {"providers": ["crossref", "openalex"]}}}
        providers = build_citation_providers(cfg)
        assert providers[0].name == "crossref"
        assert providers[1].name == "openalex"

    def test_opencitations_included(self):
        cfg = {"rag": {"citations": {"providers": ["opencitations"]}}}
        providers = build_citation_providers(cfg)
        assert len(providers) == 1
        assert providers[0].name == "opencitations"

    def test_unknown_provider_skipped(self):
        cfg = {"rag": {"citations": {"providers": ["openalex", "nonexistent"]}}}
        providers = build_citation_providers(cfg)
        assert len(providers) == 1
        assert providers[0].name == "openalex"

    def test_email_forwarded_to_openalex(self):
        cfg = {
            "rag": {"citations": {"providers": ["openalex"]}},
            "unpaywall": {"email": "user@example.com"},
        }
        providers = build_citation_providers(cfg)
        oa = providers[0]
        assert isinstance(oa, OpenAlexCitationProvider)
        assert oa._email == "user@example.com"

    def test_email_from_openalex_source_cfg(self):
        cfg = {
            "rag": {"citations": {"providers": ["openalex"]}},
            "sources": {"openalex": {"email": "oa@example.com"}},
        }
        providers = build_citation_providers(cfg)
        assert providers[0]._email == "oa@example.com"

    def test_empty_providers_list(self):
        cfg = {"rag": {"citations": {"providers": []}}}
        providers = build_citation_providers(cfg)
        assert providers == []


# ---------------------------------------------------------------------------
# Enrichment orchestrator
# ---------------------------------------------------------------------------

class TestEnrichmentOrchestrator:
    def _make_cache(self, tmp_path, papers: list[Paper]) -> Cache:
        cache = Cache(str(tmp_path / "enrich.db"))
        for p in papers:
            cache.save(p)
        return cache

    def test_enrich_citations_writes_edges(self, tmp_path):
        from mosaic.citations.enrichment import enrich_citations

        p1 = Paper(title="A", doi="10.1/a", source="test", year=2020, abstract="x")
        p2 = Paper(title="B", doi="10.1/b", source="test", year=2021, abstract="y")
        cache = self._make_cache(tmp_path, [p1, p2])

        # p1 cites p2
        work_resp = _mock_resp({"referenced_works": ["https://openalex.org/W999"]})
        batch_resp = _mock_resp({"results": [{"doi": "https://doi.org/10.1/b", "ids": {}}]})

        cfg = {"rag": {"citations": {"providers": ["openalex"], "enabled": True}}}
        with patch("httpx.get", side_effect=[work_resp, batch_resp]):
            enriched, skipped = enrich_citations([p1], cfg, cache, progress=False)

        assert enriched == 1
        assert skipped == 0
        assert cache.get_citation_links(p1.uid, {p2.uid}) == 1

    def test_enrich_citations_skips_already_enriched(self, tmp_path):
        from mosaic.citations.enrichment import enrich_citations

        p1 = Paper(title="A", doi="10.1/a", source="test", year=2020, abstract="x")
        p2 = Paper(title="B", doi="10.1/b", source="test", year=2021, abstract="y")
        cache = self._make_cache(tmp_path, [p1, p2])
        # Pre-populate edge so p1 is "already enriched"
        cache.upsert_citation_edges([(p1.uid, p2.uid, "openalex")])

        cfg = {"rag": {"citations": {"providers": ["openalex"]}}}
        with patch("httpx.get") as mock_get:
            enriched, skipped = enrich_citations([p1], cfg, cache, progress=False)

        mock_get.assert_not_called()
        assert enriched == 0
        assert skipped == 1

    def test_enrich_citations_reindex_forces_refetch(self, tmp_path):
        from mosaic.citations.enrichment import enrich_citations

        p1 = Paper(title="A", doi="10.1/a", source="test", year=2020, abstract="x")
        p2 = Paper(title="B", doi="10.1/b", source="test", year=2021, abstract="y")
        cache = self._make_cache(tmp_path, [p1, p2])
        cache.upsert_citation_edges([(p1.uid, p2.uid, "openalex")])

        work_resp = _mock_resp({"referenced_works": ["https://openalex.org/W999"]})
        batch_resp = _mock_resp({"results": [{"doi": "https://doi.org/10.1/b", "ids": {}}]})
        cfg = {"rag": {"citations": {"providers": ["openalex"]}}}

        with patch("httpx.get", side_effect=[work_resp, batch_resp]):
            enriched, _ = enrich_citations([p1], cfg, cache, reindex=True, progress=False)

        assert enriched == 1

    def test_only_local_edges_stored(self, tmp_path):
        """References to papers not in the cache must be dropped."""
        from mosaic.citations.enrichment import enrich_citations

        p1 = Paper(title="A", doi="10.1/a", source="test", year=2020, abstract="x")
        cache = self._make_cache(tmp_path, [p1])  # p2 NOT in cache

        work_resp = _mock_resp({"referenced_works": ["https://openalex.org/W999"]})
        # batch returns a DOI that is NOT in local cache
        batch_resp = _mock_resp({"results": [{"doi": "https://doi.org/10.999/remote", "ids": {}}]})
        cfg = {"rag": {"citations": {"providers": ["openalex"]}}}

        with patch("httpx.get", side_effect=[work_resp, batch_resp]):
            enriched, _ = enrich_citations([p1], cfg, cache, progress=False)

        assert enriched == 0  # no local match → edge not stored

    def test_provider_fallback(self, tmp_path):
        """When the first provider returns empty refs, the second is tried."""
        from mosaic.citations.enrichment import enrich_citations

        p1 = Paper(title="A", doi="10.1/a", source="test", year=2020, abstract="x")
        p2 = Paper(title="B", doi="10.1/b", source="test", year=2021, abstract="y")
        cache = self._make_cache(tmp_path, [p1, p2])

        # OA returns nothing; CrossRef returns p2
        oa_work_resp = _mock_resp({"referenced_works": []})
        cr_resp = _mock_resp({"message": {"reference": [{"DOI": "10.1/b"}]}})

        cfg = {"rag": {"citations": {"providers": ["openalex", "crossref"]}}}
        with patch("httpx.get", side_effect=[oa_work_resp, cr_resp]):
            enriched, _ = enrich_citations([p1], cfg, cache, progress=False)

        assert enriched == 1
        assert cache.get_citation_links(p1.uid, {p2.uid}) == 1

    def test_no_providers_returns_zero(self, tmp_path):
        from mosaic.citations.enrichment import enrich_citations

        p1 = Paper(title="A", doi="10.1/a", source="test")
        cache = self._make_cache(tmp_path, [p1])
        cfg = {"rag": {"citations": {"providers": []}}}
        enriched, skipped = enrich_citations([p1], cfg, cache, progress=False)
        assert enriched == 0
        assert skipped == 1


# ---------------------------------------------------------------------------
# DB cache citation methods
# ---------------------------------------------------------------------------

class TestCacheMethodsCitations:
    def test_upsert_and_get_links(self, tmp_cache_with_citations):
        cache, p1, p2 = tmp_cache_with_citations
        assert cache.get_citation_links(p1.uid, {p2.uid}) == 1

    def test_get_citation_links_bidirectional(self, tmp_cache_with_citations):
        """Edge p1→p2 should count for p2 looking at p1 as candidate."""
        cache, p1, p2 = tmp_cache_with_citations
        assert cache.get_citation_links(p2.uid, {p1.uid}) == 1

    def test_get_citation_links_no_candidates(self, tmp_cache_with_citations):
        cache, p1, _ = tmp_cache_with_citations
        assert cache.get_citation_links(p1.uid, set()) == 0

    def test_get_citation_links_unrelated(self, tmp_path):
        cache = Cache(str(tmp_path / "unrelated.db"))
        p1 = Paper(title="A", doi="10.1/a", source="test")
        p2 = Paper(title="B", doi="10.1/b", source="test")
        cache.save(p1)
        cache.save(p2)
        # No edges stored
        assert cache.get_citation_links(p1.uid, {p2.uid}) == 0

    def test_get_citation_neighbors(self, tmp_cache_with_citations):
        cache, p1, p2 = tmp_cache_with_citations
        neighbors = cache.get_citation_neighbors(p1.uid)
        assert p2.uid in neighbors

    def test_get_citation_neighbors_empty(self, tmp_cache_with_citations):
        cache, p1, p2 = tmp_cache_with_citations
        # p2 has no outgoing edges
        assert cache.get_citation_neighbors(p2.uid) == []

    def test_get_enriched_uids(self, tmp_cache_with_citations):
        cache, p1, _ = tmp_cache_with_citations
        enriched = cache.get_enriched_uids()
        assert p1.uid in enriched

    def test_upsert_citation_edges_deduplication(self, tmp_cache_with_citations):
        cache, p1, p2 = tmp_cache_with_citations
        # Inserting the same edge twice should not raise or duplicate
        cache.upsert_citation_edges([(p1.uid, p2.uid, "openalex")])
        assert cache.get_citation_links(p1.uid, {p2.uid}) == 1


# ---------------------------------------------------------------------------
# Graph-boosted retrieval in rag.py
# ---------------------------------------------------------------------------

class TestGraphBoostedRetrieval:
    """Tests for _citation_boost and _expand_neighbors helpers."""

    def test_citation_boost_no_alpha(self, tmp_path):
        """alpha=0 must preserve original cosine order."""
        from mosaic.rag import _citation_boost

        cache = Cache(str(tmp_path / "boost.db"))
        p1 = Paper(title="A", doi="10.1/a", source="t", abstract="x")
        p2 = Paper(title="B", doi="10.1/b", source="t", abstract="y")
        cache.save(p1)
        cache.save(p2)
        uids = [p1.uid, p2.uid]
        result = _citation_boost(uids, cache, alpha=0.0, top_k=10)
        assert result == uids  # original order preserved

    def test_citation_boost_promotes_cited_paper(self, tmp_path):
        """Paper with more citation links should rise above a paper with fewer.

        With edges p3→p1 and p3→p2 and alpha=2.0:
          score(p1, rank=0) = 1/1 * (1 + 2*1) = 3.0  (cited by p3)
          score(p3, rank=2) = 1/3 * (1 + 2*2) ≈ 1.67  (cites both p1 and p2)
          score(p2, rank=1) = 1/2 * (1 + 2*1) = 1.5   (cited by p3)
        Expected order: p1 > p3 > p2 — p3 overtakes p2 despite starting lower.
        """
        from mosaic.rag import _citation_boost

        cache = Cache(str(tmp_path / "boost2.db"))
        p1 = Paper(title="A", doi="10.1/a", source="t", abstract="x")  # rank 0
        p2 = Paper(title="B", doi="10.1/b", source="t", abstract="y")  # rank 1
        p3 = Paper(title="C", doi="10.1/c", source="t", abstract="z")  # rank 2
        for p in [p1, p2, p3]:
            cache.save(p)
        # p3 cites both p1 and p2
        cache.upsert_citation_edges([
            (p3.uid, p1.uid, "openalex"),
            (p3.uid, p2.uid, "openalex"),
        ])
        uids = [p1.uid, p2.uid, p3.uid]
        result = _citation_boost(uids, cache, alpha=2.0, top_k=10)
        assert result.index(p3.uid) < result.index(p2.uid)

    def test_expand_neighbors_adds_cached_neighbors(self, tmp_path):
        """_expand_neighbors should append citation neighbors not in the list."""
        from mosaic.rag import _expand_neighbors

        cache = Cache(str(tmp_path / "expand.db"))
        p1 = Paper(title="A", doi="10.1/a", source="t", abstract="x")
        p2 = Paper(title="B", doi="10.1/b", source="t", abstract="y")
        p3 = Paper(title="C", doi="10.1/c", source="t", abstract="z")
        for p in [p1, p2, p3]:
            cache.save(p)
        # p1 cites p3; p3 is not in the initial uid list
        cache.upsert_citation_edges([(p1.uid, p3.uid, "openalex")])
        result = _expand_neighbors([p1.uid, p2.uid], cache, top_k=5)
        assert p3.uid in result
        # Original entries preserved at original positions
        assert result[0] == p1.uid
        assert result[1] == p2.uid

    def test_expand_neighbors_no_duplicates(self, tmp_path):
        """Neighbors already in the uid list should not be added again."""
        from mosaic.rag import _expand_neighbors

        cache = Cache(str(tmp_path / "dedup.db"))
        p1 = Paper(title="A", doi="10.1/a", source="t", abstract="x")
        p2 = Paper(title="B", doi="10.1/b", source="t", abstract="y")
        for p in [p1, p2]:
            cache.save(p)
        cache.upsert_citation_edges([(p1.uid, p2.uid, "openalex")])
        result = _expand_neighbors([p1.uid, p2.uid], cache, top_k=5)
        assert result.count(p2.uid) == 1

    def test_retrieve_with_citation_boost_enabled(self, tmp_path):
        """retrieve() must call _citation_boost when citations.enabled=True."""
        from unittest.mock import patch as _patch

        from mosaic.rag import retrieve

        cache = Cache(str(tmp_path / "retrieve.db"))
        p = Paper(title="X", doi="10.1/x", source="t", abstract="hello world")
        cache.save(p)

        cfg = {
            "rag": {
                "top_k": 5,
                "citations": {"enabled": True, "boost_alpha": 0.3, "expand_neighbors": False},
                "embedding_provider": "openai",
                "embedding_model": "test",
                "embedding_api_key": "key",
                "embedding_base_url": "",
            }
        }
        fake_emb = [0.1] * 3

        with _patch("mosaic.embeddings.embed_texts", return_value=[fake_emb]):
            with _patch.object(cache, "vector_search", return_value=[p.uid]):
                with _patch("mosaic.rag._citation_boost", return_value=[p.uid]) as mock_boost:
                    retrieve("hello", cfg, cache)

        mock_boost.assert_called_once()
