"""Tests for mosaic/embeddings.py and mosaic/rag.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mosaic.models import Paper
from mosaic.rag import _build_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _paper(title: str, abstract: str = "", year: int = 2020, uid_suffix: str = "") -> Paper:
    """Build a minimal Paper with a stable DOI-based UID."""
    doi = f"10.9999/test.{title.lower().replace(' ', '')}{uid_suffix}"
    return Paper(title=title, abstract=abstract, year=year, doi=doi, source="test")


def _make_embedding_response(embeddings: list[list[float]]) -> MagicMock:
    """Build a mock httpx response that looks like an OpenAI /v1/embeddings reply."""
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {
        "data": [{"index": i, "embedding": emb} for i, emb in enumerate(embeddings)]
    }
    return m


# ---------------------------------------------------------------------------
# test_embed_texts_batching
# ---------------------------------------------------------------------------


class TestEmbedTextsBatching:
    def test_single_batch(self):
        """Small input that fits in one batch should make exactly one HTTP call."""
        from mosaic.embeddings import embed_texts

        fake_emb = [[0.1, 0.2, 0.3]]
        with patch("httpx.post", return_value=_make_embedding_response(fake_emb)) as mock_post:
            result = embed_texts(
                ["hello world"], {"model": "test-model", "api_key": "key", "base_url": ""}
            )

        assert mock_post.call_count == 1
        assert result == fake_emb

    def test_multi_batch_splitting(self):
        """Input larger than _BATCH_SIZE should trigger multiple HTTP calls."""
        from mosaic.embeddings import _BATCH_SIZE, embed_texts

        n = _BATCH_SIZE + 5
        texts = [f"text {i}" for i in range(n)]
        # Each batch returns embeddings matching the batch size
        batch1_embs = [[float(i)] for i in range(_BATCH_SIZE)]
        batch2_embs = [[float(i + _BATCH_SIZE)] for i in range(5)]

        responses = [
            _make_embedding_response(batch1_embs),
            _make_embedding_response(batch2_embs),
        ]
        with patch("httpx.post", side_effect=responses) as mock_post:
            result = embed_texts(texts, {"model": "test-model", "api_key": "key", "base_url": ""})

        assert mock_post.call_count == 2
        assert len(result) == n
        assert result[0] == [0.0]
        assert result[_BATCH_SIZE] == [float(_BATCH_SIZE)]

    def test_empty_input_returns_empty(self):
        """Empty text list should return an empty list without making any HTTP calls."""
        from mosaic.embeddings import embed_texts

        with patch("httpx.post") as mock_post:
            result = embed_texts([], {"model": "test-model", "api_key": "key", "base_url": ""})

        assert result == []
        mock_post.assert_not_called()

    def test_missing_model_raises(self):
        """Missing model name should raise ValueError."""
        from mosaic.embeddings import embed_texts

        with pytest.raises(ValueError, match="No embedding model"):
            embed_texts(["text"], {"model": "", "api_key": "key", "base_url": ""})

    def test_uses_base_url_when_provided(self):
        """When base_url is set, the request should go to base_url/v1/embeddings."""
        from mosaic.embeddings import embed_texts

        with patch("httpx.post", return_value=_make_embedding_response([[0.1]])) as mock_post:
            embed_texts(
                ["hello"],
                {"model": "m", "api_key": "k", "base_url": "http://localhost:11434"},
            )

        called_url = mock_post.call_args[0][0]
        assert called_url == "http://localhost:11434/v1/embeddings"

    def test_uses_openai_when_no_base_url(self):
        """Without a base_url the request should go to the official OpenAI endpoint."""
        from mosaic.embeddings import embed_texts

        with patch("httpx.post", return_value=_make_embedding_response([[0.5]])) as mock_post:
            embed_texts(["hello"], {"model": "m", "api_key": "sk-x", "base_url": ""})

        called_url = mock_post.call_args[0][0]
        assert called_url == "https://api.openai.com/v1/embeddings"


# ---------------------------------------------------------------------------
# test_build_context
# ---------------------------------------------------------------------------


class TestBuildContext:
    def test_basic_format(self):
        """Context should number papers, include title, authors, and year."""
        papers = [
            _paper("Attention Is All You Need", abstract="Transformer architecture.", year=2017),
        ]
        papers[0].authors = ["Vaswani", "Shazeer"]
        ctx = _build_context(papers)
        assert "[1]" in ctx
        assert "Attention Is All You Need" in ctx
        assert "2017" in ctx
        assert "Vaswani" in ctx

    def test_multiple_papers_numbered(self):
        p1 = _paper("Alpha", abstract="First paper.", year=2020)
        p2 = _paper("Beta", abstract="Second paper.", year=2021)
        ctx = _build_context([p1, p2])
        assert "[1]" in ctx
        assert "[2]" in ctx
        assert "Alpha" in ctx
        assert "Beta" in ctx

    def test_author_et_al_truncation(self):
        """More than 3 authors should show 'et al.'."""
        p = _paper("MultiAuthor", year=2022)
        p.authors = ["A", "B", "C", "D", "E"]
        ctx = _build_context([p])
        assert "et al." in ctx

    def test_missing_abstract_handled(self):
        """Papers without abstracts should not raise an error."""
        p = _paper("No Abstract", year=2023)
        p.abstract = None
        ctx = _build_context([p])
        assert "No Abstract" in ctx

    def test_empty_list_returns_empty_string(self):
        assert _build_context([]) == ""

    def test_abstract_truncated_to_400(self):
        """Abstract snippet should not exceed 400 characters."""
        long_abstract = "x" * 600
        p = _paper("Long", abstract=long_abstract, year=2020)
        ctx = _build_context([p])
        # The snippet in the context should be at most 400 x's
        snippet = "x" * 400
        assert snippet in ctx
        assert "x" * 401 not in ctx


# ---------------------------------------------------------------------------
# test_index_papers_model_change_raises
# ---------------------------------------------------------------------------


class TestIndexPapersModelChange:
    def test_model_change_without_reindex_raises(self, tmp_cache):
        """If the stored model differs from the current one, a ValueError should be raised."""
        from mosaic.rag import index_papers

        # Simulate a stored model name
        tmp_cache.set_rag_meta("embedding_model", "old-model")

        papers = [_paper("Some Paper", abstract="abstract")]
        cfg = {
            "rag": {
                "embedding_model": "new-model",
                "embedding_base_url": "",
                "embedding_api_key": "",
                "embedding_provider": "",
                "top_k": 10,
            },
            "llm": {},
        }
        with pytest.raises(ValueError, match="Embedding model changed"):
            index_papers(papers, cfg, tmp_cache, reindex=False, progress=False)

    def test_reindex_flag_allows_model_change(self, tmp_cache):
        """With --reindex, a model change should be allowed (no ValueError)."""
        from mosaic.rag import index_papers

        tmp_cache.set_rag_meta("embedding_model", "old-model")

        papers = [_paper("Some Paper", abstract="abstract")]
        cfg = {
            "rag": {
                "embedding_model": "new-model",
                "embedding_base_url": "http://localhost:11434",
                "embedding_api_key": "key",
                "embedding_provider": "",
                "top_k": 10,
            },
            "llm": {},
        }

        fake_emb = [[0.1, 0.2, 0.3]]
        with patch("mosaic.embeddings.embed_texts", return_value=fake_emb):
            with patch.object(tmp_cache, "upsert_embeddings_batch"):
                # Should not raise
                newly, skipped = index_papers(papers, cfg, tmp_cache, reindex=True, progress=False)

        assert newly == 1

    def test_no_model_configured_raises(self, tmp_cache):
        """If no embedding model is configured, a ValueError should be raised immediately."""
        from mosaic.rag import index_papers

        papers = [_paper("Some Paper", abstract="abstract")]
        cfg = {
            "rag": {
                "embedding_model": "",
                "embedding_base_url": "",
                "embedding_api_key": "",
                "embedding_provider": "",
                "top_k": 10,
            },
            "llm": {},
        }
        with pytest.raises(ValueError, match="No embedding model"):
            index_papers(papers, cfg, tmp_cache, progress=False)


# ---------------------------------------------------------------------------
# test_retrieve_returns_papers_in_order
# ---------------------------------------------------------------------------


class TestRetrieveOrder:
    def test_papers_returned_in_similarity_order(self, tmp_cache):
        """retrieve() should return papers in the same order as vector_search() results."""
        from mosaic.rag import retrieve

        # Put two papers in the cache
        p1 = _paper("First", abstract="first paper", year=2021, uid_suffix="1")
        p2 = _paper("Second", abstract="second paper", year=2022, uid_suffix="2")
        tmp_cache.save(p1)
        tmp_cache.save(p2)

        cfg = {
            "rag": {
                "embedding_model": "test-model",
                "embedding_base_url": "",
                "embedding_api_key": "key",
                "embedding_provider": "",
                "top_k": 5,
            },
            "llm": {},
        }

        query_vec = [0.1, 0.2, 0.3]
        # Simulate vector_search returning p2 before p1 (p2 is more similar)
        with patch("mosaic.embeddings.embed_texts", return_value=[query_vec]):
            with patch.object(tmp_cache, "vector_search", return_value=[p2.uid, p1.uid]):
                papers = retrieve("some query", cfg, tmp_cache)

        assert len(papers) == 2
        assert papers[0].uid == p2.uid
        assert papers[1].uid == p1.uid

    def test_pre_filter_restricts_results(self, tmp_cache):
        """pre_filter should restrict the returned papers to the allowed UIDs."""
        from mosaic.rag import retrieve

        p1 = _paper("Alpha", abstract="alpha text", year=2020, uid_suffix="a")
        p2 = _paper("Beta", abstract="beta text", year=2021, uid_suffix="b")
        tmp_cache.save(p1)
        tmp_cache.save(p2)

        cfg = {
            "rag": {
                "embedding_model": "test-model",
                "embedding_base_url": "",
                "embedding_api_key": "key",
                "embedding_provider": "",
                "top_k": 5,
            },
            "llm": {},
        }

        query_vec = [0.5, 0.5]
        # vector_search returns both, but pre_filter only allows p1
        with patch("mosaic.embeddings.embed_texts", return_value=[query_vec]):
            with patch.object(tmp_cache, "vector_search", return_value=[p1.uid, p2.uid]):
                papers = retrieve("some query", cfg, tmp_cache, pre_filter=[p1.uid])

        assert len(papers) == 1
        assert papers[0].uid == p1.uid

    def test_empty_vector_search_returns_empty(self, tmp_cache):
        """When vector_search returns nothing, retrieve should return an empty list."""
        from mosaic.rag import retrieve

        cfg = {
            "rag": {
                "embedding_model": "test-model",
                "embedding_base_url": "",
                "embedding_api_key": "key",
                "embedding_provider": "",
                "top_k": 5,
            },
            "llm": {},
        }
        with patch("mosaic.embeddings.embed_texts", return_value=[[0.1]]):
            with patch.object(tmp_cache, "vector_search", return_value=[]):
                papers = retrieve("some query", cfg, tmp_cache)

        assert papers == []


# ---------------------------------------------------------------------------
# test_get_embedding_cfg (config helper)
# ---------------------------------------------------------------------------


class TestGetEmbeddingCfg:
    def test_rag_overrides_llm(self):
        from mosaic.config import get_embedding_cfg

        cfg = {
            "rag": {
                "embedding_model": "arctic",
                "embedding_base_url": "http://emb:11434",
                "embedding_api_key": "emb-key",
                "embedding_provider": "openai",
            },
            "llm": {
                "provider": "anthropic",
                "api_key": "llm-key",
                "base_url": "http://llm:8080",
            },
        }
        result = get_embedding_cfg(cfg)
        assert result["model"] == "arctic"
        assert result["base_url"] == "http://emb:11434"
        assert result["api_key"] == "emb-key"
        assert result["provider"] == "openai"

    def test_falls_back_to_llm(self):
        from mosaic.config import get_embedding_cfg

        cfg = {
            "rag": {
                "embedding_model": "arctic",
                "embedding_base_url": "",
                "embedding_api_key": "",
                "embedding_provider": "",
            },
            "llm": {
                "provider": "openai",
                "api_key": "sk-123",
                "base_url": "http://localhost:11434/v1",
            },
        }
        result = get_embedding_cfg(cfg)
        assert result["model"] == "arctic"
        assert result["base_url"] == "http://localhost:11434/v1"
        assert result["api_key"] == "sk-123"
        assert result["provider"] == "openai"


# ---------------------------------------------------------------------------
# TestSemanticSearch
# ---------------------------------------------------------------------------

_CFG_EMB = {
    "rag": {
        "embedding_model": "test-model",
        "embedding_base_url": "http://localhost:11434",
        "embedding_api_key": "test-key",
        "embedding_provider": "openai",
        "top_k": 10,
        "citations": {"enabled": False},
    },
    "llm": {},
}


def _make_emb_response(vecs: list[list[float]]) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"data": [{"index": i, "embedding": v} for i, v in enumerate(vecs)]}
    return m


class TestSemanticSearch:
    def test_returns_papers_with_scores(self, tmp_path):
        """semantic_search scores each paper and sorts by similarity."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            import pytest

            pytest.skip("sqlite-vec not installed")

        from mosaic.db import Cache
        from mosaic.rag import semantic_search

        cache = Cache(str(tmp_path / "sem.db"))
        dim = 2
        p1 = _paper("Paper Alpha", abstract="alpha")
        p2 = _paper("Paper Beta", abstract="beta")
        cache.save(p1)
        cache.save(p2)
        cache.upsert_embeddings_batch([(p1.uid, [1.0, 0.0]), (p2.uid, [0.0, 1.0])], dim)

        # Query embedding == p1's embedding → p1 is closest
        with patch("httpx.post", return_value=_make_emb_response([[1.0, 0.0]])):
            results = semantic_search("alpha query", cache, _CFG_EMB, k=2)

        assert len(results) == 2
        assert results[0].uid == p1.uid
        assert results[0].relevance_score is not None
        assert 0.0 < results[0].relevance_score <= 1.0
        # Closest paper has higher score than the farther one
        assert results[0].relevance_score > results[1].relevance_score

    def test_no_vec_table_raises_runtime_error(self, tmp_path):
        """If vec_papers does not exist, raise RuntimeError with helpful message."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            import pytest

            pytest.skip("sqlite-vec not installed")

        import pytest

        from mosaic.db import Cache
        from mosaic.rag import semantic_search

        cache = Cache(str(tmp_path / "empty.db"))
        with patch("httpx.post", return_value=_make_emb_response([[0.1, 0.2]])):
            with pytest.raises(RuntimeError, match="mosaic index"):
                semantic_search("query", cache, _CFG_EMB, k=5)

    def test_downloaded_only_filters_results(self, tmp_path):
        """downloaded_only=True should exclude papers without an ok download."""
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            import pytest

            pytest.skip("sqlite-vec not installed")

        from mosaic.db import Cache
        from mosaic.rag import semantic_search

        cache = Cache(str(tmp_path / "dl.db"))
        dim = 2
        p_dl = _paper("Downloaded", uid_suffix="-dl")
        p_nd = _paper("Not Downloaded", uid_suffix="-nd")
        cache.save(p_dl)
        cache.save(p_nd)
        cache.upsert_embeddings_batch(
            [(p_dl.uid, [1.0, 0.0]), (p_nd.uid, [0.9, 0.1])], dim
        )
        cache.set_download(p_dl.uid, "/tmp/dl.pdf", "ok")

        with patch("httpx.post", return_value=_make_emb_response([[1.0, 0.0]])):
            results = semantic_search("query", cache, _CFG_EMB, k=10, downloaded_only=True)

        uids = {p.uid for p in results}
        assert p_dl.uid in uids
        assert p_nd.uid not in uids

    def test_empty_embedding_response_returns_empty(self, tmp_path):
        """If embed_texts returns nothing, semantic_search returns []."""
        from mosaic.db import Cache
        from mosaic.rag import semantic_search

        cache = Cache(str(tmp_path / "noemb.db"))
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"data": []}
        with patch("httpx.post", return_value=m):
            results = semantic_search("query", cache, _CFG_EMB, k=5)
        assert results == []
