"""Regression tests for the RAG / vector-index fixes (chunking, retrieval, index lifecycle)."""

from __future__ import annotations

import sqlite3
from itertools import pairwise
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mosaic.db import Cache
from mosaic.models import Paper
from mosaic.rag import (
    LEGACY_INDEX_MESSAGE,
    NO_INDEX_MESSAGE,
    NO_PYMUPDF_MESSAGE,
    NO_SUBSET_MESSAGE,
    _build_context,
    _call_llm,
    _chunk_text,
    _history_messages,
    ask,
    chat_turn,
    index_health,
    index_papers,
    retrieve,
    retrieve_with_context,
    semantic_search,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CFG = {
    "rag": {
        "embedding_model": "test-model",
        "embedding_base_url": "",
        "embedding_api_key": "key",
        "top_k": 5,
        "chunk_size": 100,
        "chunk_overlap": 20,
        "full_text_index": True,
        "citations": {"enabled": False},
    },
    "llm": {"provider": "openai", "api_key": "sk-test", "model": "m", "base_url": ""},
}


def _cfg(**rag_overrides) -> dict:
    cfg = {"rag": {**_CFG["rag"], **rag_overrides}, "llm": dict(_CFG["llm"])}
    return cfg


def _p(name: str, abstract: str = "", **kw) -> Paper:
    return Paper(title=name, abstract=abstract, doi=f"10.9/{name.lower()}", source="test", **kw)


def _vec(text: str) -> list[float]:
    """Deterministic 2-d embedding: 'alpha' texts point one way, 'beta' texts the other."""
    t = text.lower()
    if "alpha" in t:
        return [1.0, 0.0]
    if "beta" in t:
        return [0.0, 1.0]
    return [0.6, 0.8]


def _fake_embed(texts, cfg, **kw):
    return [_vec(t) for t in texts]


@pytest.fixture
def vec_cache(tmp_path):
    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        pytest.skip("sqlite-vec not installed")
    cache = Cache(str(tmp_path / "vec.db"))
    if not cache.vec_available:
        pytest.skip("sqlite-vec could not be loaded")
    return cache


def _chunk_count(cache: Cache, uid: str) -> int:
    return cache.con.execute("SELECT COUNT(*) FROM paper_chunks WHERE uid=?", (uid,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class TestChunker:
    TEXT = " ".join(f"word{i:04d}" for i in range(600))  # ~5400 chars

    def test_no_redundant_tail_chunk(self):
        chunks = _chunk_text(self.TEXT, chunk_chars=1000, overlap_chars=200)
        assert chunks[-1][2] == len(self.TEXT)
        for (_, s_prev, e_prev), (_, s, e) in pairwise(chunks):
            # A chunk fully inside the previous one would be redundant
            assert not (s >= s_prev and e <= e_prev)
            assert s < e_prev  # still overlapping

    def test_chunks_start_on_word_boundary(self):
        chunks = _chunk_text(self.TEXT, chunk_chars=1000, overlap_chars=203)
        for chunk, start, _ in chunks[1:]:
            assert self.TEXT[start - 1].isspace()
            assert chunk.startswith("word")

    def test_full_coverage(self):
        chunks = _chunk_text(self.TEXT, chunk_chars=700, overlap_chars=100)
        covered = 0
        for _, start, end in chunks:
            assert start <= covered
            covered = max(covered, end)
        assert covered == len(self.TEXT)

    @pytest.mark.parametrize(("size", "overlap"), [(0, 0), (-5, 0), (100, -1), (100, 100)])
    def test_invalid_settings_raise(self, size, overlap):
        with pytest.raises(ValueError):
            _chunk_text(self.TEXT, chunk_chars=size, overlap_chars=overlap)

    @pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, -1), (100, 150)])
    def test_index_papers_validates_chunk_config(self, tmp_cache, size, overlap):
        cfg = _cfg(chunk_size=size, chunk_overlap=overlap)
        with pytest.raises(ValueError, match=r"rag\.chunk_"):
            index_papers([_p("Alpha")], cfg, tmp_cache, progress=False)

    def test_default_chunk_size_comes_from_config_defaults(self, tmp_cache):
        from mosaic.config import _DEFAULTS

        cfg = _cfg()
        del cfg["rag"]["chunk_size"]
        del cfg["rag"]["chunk_overlap"]
        text = "alpha " * 3000
        paper = _p("Alpha", "alpha")
        tmp_cache.save(paper)
        tmp_cache.set_download(paper.uid, "/tmp/a.pdf", "ok")
        with (
            patch("mosaic.pdf.is_available", return_value=True),
            patch("mosaic.pdf.extract_text", return_value=text),
            patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed),
            patch.object(tmp_cache, "upsert_chunks_batch") as mock_upsert,
        ):
            index_papers([paper], cfg, tmp_cache, progress=False)
        rows = mock_upsert.call_args.args[0]
        max_len = max(len(r[3]) for r in rows)
        assert max_len <= _DEFAULTS["rag"]["chunk_size"] * 4


# ---------------------------------------------------------------------------
# Database layer (sqlite-vec)
# ---------------------------------------------------------------------------


class TestVecStorage:
    def test_legacy_upsert_is_idempotent(self, vec_cache):
        vec_cache.upsert_embedding("doi:10.9/a", [1.0, 0.0], 2)
        vec_cache.upsert_embedding("doi:10.9/a", [0.0, 1.0], 2)
        assert vec_cache.vector_search_scored([0.0, 1.0], 5) == [("doi:10.9/a", 0.0)]

    def test_duplicate_chunk_ids_in_one_batch(self, vec_cache):
        rows = [
            ("u::0", "u", 0, "first", 0, 5, [1.0, 0.0]),
            ("u::0", "u", 0, "second", 0, 6, [0.0, 1.0]),
        ]
        vec_cache.upsert_chunks_batch(rows, 2)
        assert vec_cache.get_chunk_texts(["u::0"]) == {"u::0": "second"}

    def test_upsert_replaces_whole_chunk_set(self, vec_cache):
        vec_cache.upsert_chunks_batch(
            [(f"u::{i}", "u", i, f"t{i}", 0, 1, [1.0, 0.0]) for i in range(3)], 2
        )
        vec_cache.upsert_chunks_batch([("u::0", "u", 0, "only", 0, 4, [1.0, 0.0])], 2)
        assert _chunk_count(vec_cache, "u") == 1
        assert [c for c, _ in vec_cache.vector_search_chunks([1.0, 0.0], 10)] == ["u::0"]

    def test_failed_upsert_rolls_back(self, vec_cache):
        vec_cache.upsert_chunks_batch([("u::0", "u", 0, "keep me", 0, 7, [1.0, 0.0])], 2)
        with pytest.raises(sqlite3.OperationalError, match="imension"):
            vec_cache.upsert_chunks_batch([("u::0", "u", 0, "bad", 0, 3, [1.0, 0.0, 0.0])], 3)
        assert not vec_cache.con.in_transaction
        assert vec_cache.get_chunk_texts(["u::0"]) == {"u::0": "keep me"}
        # Another connection can write immediately (no dangling lock)
        other = Cache(vec_cache._db_path)
        other.save(_p("Other"))

    def test_vector_search_chunks_reraises_errors(self, vec_cache):
        vec_cache.upsert_chunks_batch([("u::0", "u", 0, "t", 0, 1, [1.0, 0.0])], 2)
        with pytest.raises(sqlite3.OperationalError):
            vec_cache.vector_search_chunks([1.0, 0.0, 0.0], 5)  # wrong dimension

    def test_k_is_clamped_to_sqlite_vec_limit(self, vec_cache):
        vec_cache.upsert_chunks_batch([("u::0", "u", 0, "t", 0, 1, [1.0, 0.0])], 2)
        assert len(vec_cache.vector_search_chunks([1.0, 0.0], 100_000)) == 1

    def test_get_chunk_texts_full_text_only(self, vec_cache):
        vec_cache.upsert_chunks_batch(
            [("m::0", "m", 0, "meta", 0, 4, [1.0, 0.0]), ("f::0", "f", 0, "pdf", 0, 3, [1.0, 0.0])],
            2,
            text_sources={"f": "pdf"},
        )
        assert vec_cache.get_chunk_texts(["m::0", "f::0"], full_text_only=True) == {"f::0": "pdf"}
        assert vec_cache.get_metadata_only_uids() == {"m"}

    def test_clear_refuses_before_deleting_without_sqlite_vec(self, vec_cache):
        vec_cache.save(_p("Alpha"))
        vec_cache.upsert_chunks_batch([("u::0", "u", 0, "t", 0, 1, [1.0, 0.0])], 2)
        vec_cache._vec_available = False
        with pytest.raises(RuntimeError, match="sqlite-vec"):
            vec_cache.clear()
        with pytest.raises(RuntimeError, match="sqlite-vec"):
            vec_cache.rebuild_vec_table()
        assert vec_cache.count_papers() == 1
        assert _chunk_count(vec_cache, "u") == 1

    def test_clear_wipes_everything(self, vec_cache):
        vec_cache.save(_p("Alpha"))
        vec_cache.upsert_chunks_batch([("u::0", "u", 0, "t", 0, 1, [1.0, 0.0])], 2)
        vec_cache.clear()
        assert vec_cache.count_papers() == 0
        assert vec_cache.vec_tables() == set()


class TestDbWithoutVec:
    def test_clear_without_vec_tables_works(self, tmp_cache):
        tmp_cache.save(_p("Alpha"))
        tmp_cache._vec_available = False
        tmp_cache.clear()
        assert tmp_cache.count_papers() == 0

    def test_upsert_fills_missing_year(self, tmp_cache):
        tmp_cache.save(Paper(title="T", doi="10.9/y", source="a", authors=["A"], abstract="x"))
        tmp_cache.save(Paper(title="T", doi="10.9/y", source="b", year=2021))
        stored = tmp_cache.get_by_uid("doi:10.9/y")
        assert stored.year == 2021
        assert stored.source == "a"
        assert tmp_cache.is_rich(stored.uid)

    def test_upsert_keeps_existing_year(self, tmp_cache):
        tmp_cache.save(Paper(title="T", doi="10.9/y2", source="a", year=2019))
        tmp_cache.save(Paper(title="T", doi="10.9/y2", source="b", year=2021))
        assert tmp_cache.get_by_uid("doi:10.9/y2").year == 2019

    def test_failed_write_does_not_leave_transaction_open(self, tmp_cache):
        bad = Paper(title=None, doi="10.9/bad", source="x")  # title is NOT NULL
        with pytest.raises(sqlite3.IntegrityError):
            tmp_cache.save(bad)
        assert not tmp_cache.con.in_transaction

    @pytest.mark.parametrize(
        "query", ["10.9/ABC", "https://doi.org/10.9/abc", "http://doi.org/10.9/Abc"]
    )
    def test_get_by_doi(self, tmp_cache, query):
        tmp_cache.save(Paper(title="By DOI", doi="10.9/abc", source="x"))
        found = tmp_cache.get_by_doi(query)
        assert found is not None and found.title == "By DOI"

    def test_get_by_doi_arxiv_form(self, tmp_cache):
        tmp_cache.save(Paper(title="Attention", arxiv_id="1706.03762", source="arXiv"))
        assert tmp_cache.get_by_doi("10.48550/arXiv.1706.03762").title == "Attention"

    def test_get_by_doi_missing(self, tmp_cache):
        assert tmp_cache.get_by_doi("") is None
        assert tmp_cache.get_by_doi("10.9/none") is None

    def test_text_source_migration_marks_multi_chunk_papers(self, tmp_path):
        db = str(tmp_path / "old.db")
        con = sqlite3.connect(db)
        con.execute(
            "CREATE TABLE paper_chunks (chunk_id TEXT PRIMARY KEY, uid TEXT NOT NULL, "
            "chunk_idx INTEGER NOT NULL, text TEXT NOT NULL, char_start INTEGER NOT NULL, "
            "char_end INTEGER NOT NULL)"
        )
        con.executemany(
            "INSERT INTO paper_chunks VALUES (?,?,?,?,?,?)",
            [("a::0", "a", 0, "t", 0, 1), ("a::1", "a", 1, "t", 1, 2), ("b::0", "b", 0, "t", 0, 1)],
        )
        con.commit()
        con.close()
        cache = Cache(db)
        assert cache.get_metadata_only_uids() == {"b"}


# ---------------------------------------------------------------------------
# Indexing lifecycle
# ---------------------------------------------------------------------------


def _pdf_patches(texts: dict[str, str]):
    """Patch pymupdf availability and extraction with per-path texts."""
    return (
        patch("mosaic.pdf.is_available", return_value=True),
        patch("mosaic.pdf.extract_text", side_effect=lambda path, **kw: texts.get(path, "")),
    )


class TestIndexLifecycle:
    def test_semantic_search_on_index_built_by_index_papers(self, vec_cache):
        pa, pb = _p("Alpha paper", "alpha"), _p("Beta paper", "beta")
        for p in (pa, pb):
            vec_cache.save(p)
        with patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            index_papers([pa, pb], _cfg(full_text_index=False), vec_cache, progress=False)
            results = semantic_search("alpha", vec_cache, _cfg(), k=2)
        assert [p.uid for p in results] == [pa.uid, pb.uid]
        assert results[0].relevance_score == pytest.approx(1.0)
        assert "vec_papers" not in vec_cache.vec_tables()

    def test_semantic_search_downloaded_only_on_chunk_index(self, vec_cache):
        pa, pb = _p("Alpha one", "alpha"), _p("Alpha two", "alpha")
        for p in (pa, pb):
            vec_cache.save(p)
        vec_cache.set_download(pb.uid, "/tmp/b.pdf", "ok")
        with patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            index_papers([pa, pb], _cfg(full_text_index=False), vec_cache, progress=False)
            results = semantic_search("alpha", vec_cache, _cfg(), k=5, downloaded_only=True)
        assert [p.uid for p in results] == [pb.uid]

    def test_narrow_subset_still_retrieved(self, vec_cache):
        near = [_p(f"Alpha{i}", "alpha") for i in range(30)]
        far = _p("Beta target", "beta")
        for p in [*near, far]:
            vec_cache.save(p)
        with patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            index_papers([*near, far], _cfg(full_text_index=False), vec_cache, progress=False)
            papers = retrieve("alpha", _cfg(top_k=1), vec_cache, pre_filter=[far.uid])
        assert [p.uid for p in papers] == [far.uid]

    def test_long_pdf_does_not_crowd_out_other_papers(self, vec_cache):
        long_paper = _p("Long", "gamma")
        others = [_p(f"Other{i}", "alpha") for i in range(4)]
        for p in [long_paper, *others]:
            vec_cache.save(p)
        vec_cache.set_download(long_paper.uid, "/tmp/long.pdf", "ok")
        pdf = _pdf_patches({"/tmp/long.pdf": "alpha " * 20_000})  # hundreds of alpha chunks
        with pdf[0], pdf[1], patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            index_papers([long_paper, *others], _cfg(), vec_cache, progress=False)
            papers, chunk_texts = retrieve_with_context("alpha", _cfg(top_k=3), vec_cache)
        assert len(papers) == 3
        assert len({p.uid for p in papers}) == 3
        # Only the PDF paper contributes an excerpt; metadata papers use their abstract
        assert all(cid.startswith(long_paper.uid) for cid in chunk_texts)

    def test_legacy_only_index_blocks_incremental_index(self, vec_cache):
        old, new = _p("Old", "alpha"), _p("New", "beta")
        for p in (old, new):
            vec_cache.save(p)
        vec_cache.upsert_embeddings_batch([(old.uid, [1.0, 0.0])], 2)
        assert LEGACY_INDEX_MESSAGE in index_health(_cfg(), vec_cache)
        with patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            with pytest.raises(ValueError, match="--reindex"):
                index_papers([new], _cfg(), vec_cache, progress=False)
            # Retrieval still works on the legacy index meanwhile
            assert [p.uid for p in retrieve("alpha", _cfg(), vec_cache)] == [old.uid]
            # --reindex rebuilds everything in the chunk format
            newly, _, _ = index_papers([old, new], _cfg(), vec_cache, reindex=True, progress=False)
        assert newly == 2
        assert vec_cache.vec_tables() == {"vec_chunks"}
        assert index_health(_cfg(full_text_index=False), vec_cache) == []

    def test_mixed_index_heals_and_drops_legacy_table(self, vec_cache):
        old, new = _p("Old", "alpha"), _p("New", "beta")
        for p in (old, new):
            vec_cache.save(p)
        vec_cache.upsert_embeddings_batch([(old.uid, [1.0, 0.0])], 2)
        vec_cache.upsert_chunks_batch([(f"{new.uid}::0", new.uid, 0, "beta", 0, 4, [0.0, 1.0])], 2)
        cfg = _cfg(full_text_index=False)
        assert any("old per-paper index" in w for w in index_health(cfg, vec_cache))
        with patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            newly, skipped, _ = index_papers([old, new], cfg, vec_cache, progress=False)
            assert (newly, skipped) == (1, 1)
            assert [p.uid for p in retrieve("alpha", _cfg(top_k=1), vec_cache)] == [old.uid]
        assert "vec_papers" not in vec_cache.vec_tables()

    def test_failure_mid_run_leaves_no_half_indexed_paper(self, vec_cache):
        pa, pb, pc = _p("Alpha A", "alpha"), _p("Alpha B", "alpha"), _p("Alpha C", "alpha")
        for p in (pa, pb, pc):
            vec_cache.save(p)
            vec_cache.set_download(p.uid, f"/tmp/{p.title}.pdf", "ok")
        texts = {f"/tmp/{p.title}.pdf": "alpha " * 600 for p in (pa, pb, pc)}  # ~9 chunks each
        calls = {"n": 0}

        def flaky(batch, cfg, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("Embedding request failed: HTTP 500")
            return _fake_embed(batch, cfg)

        pdf = _pdf_patches(texts)
        with pdf[0], pdf[1], patch("mosaic.embeddings.embed_texts", side_effect=flaky):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                index_papers([pa, pb, pc], _cfg(), vec_cache, progress=False, batch_size=5)
            first_count = _chunk_count(vec_cache, pa.uid)
            assert first_count > 1
            assert _chunk_count(vec_cache, pb.uid) == 0
            assert vec_cache.get_indexed_uids() == {pa.uid}
            # Next run picks up exactly the missing papers
            newly, skipped, ft = index_papers(
                [pa, pb, pc], _cfg(), vec_cache, progress=False, batch_size=5
            )
        assert (newly, skipped, ft) == (2, 1, 2)
        assert _chunk_count(vec_cache, pb.uid) == first_count

    def test_metadata_only_paper_upgraded_when_pdf_arrives(self, vec_cache):
        paper = _p("Alpha", "alpha abstract")
        vec_cache.save(paper)
        with patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            with patch("mosaic.pdf.is_available", return_value=True):
                assert index_papers([paper], _cfg(), vec_cache, progress=False) == (1, 0, 0)
            assert _chunk_count(vec_cache, paper.uid) == 1

            vec_cache.set_download(paper.uid, "/tmp/alpha.pdf", "ok")
            pdf = _pdf_patches({"/tmp/alpha.pdf": "alpha body " * 500})
            with pdf[0], pdf[1]:
                assert index_papers([paper], _cfg(), vec_cache, progress=False) == (1, 0, 1)
                n_chunks = _chunk_count(vec_cache, paper.uid)
                assert n_chunks > 1
                texts = vec_cache.get_chunk_texts([f"{paper.uid}::0"])
                assert not texts[f"{paper.uid}::0"].startswith("Title:")
                # Already full text: nothing to do on the next run
                assert index_papers([paper], _cfg(), vec_cache, progress=False) == (0, 1, 0)

    def test_unreadable_pdf_is_not_retried_every_run(self, vec_cache):
        paper = _p("Scanned", "alpha")
        vec_cache.save(paper)
        vec_cache.set_download(paper.uid, "/tmp/scan.pdf", "ok")
        pdf = _pdf_patches({})  # extraction yields no text
        with pdf[0], pdf[1], patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed):
            assert index_papers([paper], _cfg(), vec_cache, progress=False) == (1, 0, 0)
            assert index_papers([paper], _cfg(), vec_cache, progress=False) == (0, 1, 0)

    def test_batch_size_is_passed_to_embedding_calls(self, tmp_cache):
        papers = [_p(f"Alpha{i}", "alpha") for i in range(5)]
        with (
            patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed) as mock_embed,
            patch.object(tmp_cache, "upsert_chunks_batch") as mock_upsert,
        ):
            newly, _, _ = index_papers(
                papers, _cfg(full_text_index=False), tmp_cache, progress=False, batch_size=2
            )
        assert newly == 5
        assert mock_upsert.call_count == 3  # 2 + 2 + 1 papers
        assert all(c.kwargs["batch_size"] == 2 for c in mock_embed.call_args_list)

    def test_duplicate_input_papers_indexed_once(self, tmp_cache):
        paper = _p("Alpha", "alpha")
        with (
            patch("mosaic.embeddings.embed_texts", side_effect=_fake_embed),
            patch.object(tmp_cache, "upsert_chunks_batch") as mock_upsert,
        ):
            newly, skipped, _ = index_papers(
                [paper, paper], _cfg(full_text_index=False), tmp_cache, progress=False
            )
        assert (newly, skipped) == (1, 1)
        assert len(mock_upsert.call_args.args[0]) == 1


# ---------------------------------------------------------------------------
# Retrieval consistency checks
# ---------------------------------------------------------------------------


class TestRetrievalChecks:
    def test_model_mismatch_at_query_time(self, tmp_cache):
        tmp_cache.set_rag_meta("embedding_model", "old-model")
        with patch("mosaic.embeddings.embed_texts", return_value=[[1.0, 0.0]]):
            with pytest.raises(ValueError, match="Embedding model changed"):
                retrieve("q", _cfg(), tmp_cache)
            with pytest.raises(ValueError, match="--reindex"):
                semantic_search("q", tmp_cache, _cfg())

    def test_missing_sqlite_vec_reported(self, tmp_cache):
        err = sqlite3.OperationalError("no such module: vec0")
        with (
            patch("mosaic.embeddings.embed_texts", return_value=[[1.0, 0.0]]),
            patch.object(tmp_cache, "vector_search_chunks", side_effect=err),
        ):
            with pytest.raises(RuntimeError, match="sqlite-vec is not installed"):
                retrieve("q", _cfg(), tmp_cache)

    def test_expand_neighbors_adds_citation_neighbors(self, tmp_cache):
        hits = [_p(f"Hit{i}", "x") for i in range(5)]
        neighbor = _p("Neighbor", "x")
        for p in [*hits, neighbor]:
            tmp_cache.save(p)
        tmp_cache.upsert_citation_edges([(hits[0].uid, neighbor.uid, "openalex")])
        cfg = _cfg(citations={"enabled": True, "boost_alpha": 0.0, "expand_neighbors": True})
        with (
            patch("mosaic.embeddings.embed_texts", return_value=[[1.0, 0.0]]),
            patch.object(tmp_cache, "vector_search", return_value=[p.uid for p in hits]),
        ):
            papers = retrieve("q", cfg, tmp_cache)
        uids = [p.uid for p in papers]
        assert len(uids) == 5
        assert neighbor.uid in uids
        assert uids[0] == hits[0].uid

    def test_expand_neighbors_respects_pre_filter(self, tmp_cache):
        hits = [_p(f"Hit{i}", "x") for i in range(3)]
        neighbor = _p("Neighbor", "x")
        for p in [*hits, neighbor]:
            tmp_cache.save(p)
        tmp_cache.upsert_citation_edges([(hits[0].uid, neighbor.uid, "openalex")])
        cfg = _cfg(citations={"enabled": True, "boost_alpha": 0.0, "expand_neighbors": True})
        subset = [p.uid for p in hits]
        with (
            patch("mosaic.embeddings.embed_texts", return_value=[[1.0, 0.0]]),
            patch.object(
                tmp_cache, "nearest_papers_for_uids", return_value=[(u, 0.1) for u in subset]
            ),
        ):
            papers = retrieve("q", cfg, tmp_cache, pre_filter=subset)
        assert neighbor.uid not in {p.uid for p in papers}

    def test_index_health_reports_pymupdf_and_model(self, tmp_cache):
        tmp_cache.set_rag_meta("embedding_model", "old-model")
        with patch("mosaic.pdf.is_available", return_value=False):
            warnings = index_health(_cfg(), tmp_cache)
        assert NO_PYMUPDF_MESSAGE in warnings
        assert any("Embedding model changed" in w for w in warnings)


# ---------------------------------------------------------------------------
# ask / chat_turn / LLM
# ---------------------------------------------------------------------------


class TestAskAndChat:
    def test_empty_subset_message(self, tmp_cache):
        with patch("mosaic.rag.retrieve_with_context") as mock_ret:
            assert ask("q", _cfg(), tmp_cache, pre_filter=[]) == (NO_SUBSET_MESSAGE, [])
            assert chat_turn("q", [], _cfg(), tmp_cache, pre_filter=[]) == (NO_SUBSET_MESSAGE, [])
        mock_ret.assert_not_called()

    def test_subset_without_indexed_papers(self, tmp_cache):
        with patch("mosaic.rag.retrieve_with_context", return_value=([], {})):
            assert ask("q", _cfg(), tmp_cache, pre_filter=["doi:x"]) == (NO_SUBSET_MESSAGE, [])
            assert ask("q", _cfg(), tmp_cache) == (NO_INDEX_MESSAGE, [])

    def test_ask_sends_single_prompt(self, tmp_cache):
        paper = _p("Alpha", "alpha abstract")
        with (
            patch("mosaic.rag.retrieve_with_context", return_value=([paper], {})),
            patch("mosaic.rag._call_llm", return_value="answer") as mock_llm,
        ):
            answer, papers = ask("what is alpha?", _cfg(), tmp_cache, mode="gaps")
        assert (answer, papers) == ("answer", [paper])
        prompt = mock_llm.call_args.args[0]
        assert isinstance(prompt, str)
        assert "what is alpha?" in prompt and "alpha abstract" in prompt

    def test_chat_turn_sends_history_then_context_prompt(self, tmp_cache):
        paper = _p("Alpha", "alpha abstract")
        history = []
        for i in range(5):
            history += [
                {"role": "user", "content": f"q{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ]
        with (
            patch("mosaic.rag.retrieve_with_context", return_value=([paper], {})),
            patch("mosaic.rag._call_llm", return_value="answer") as mock_llm,
        ):
            answer, papers = chat_turn("follow-up?", history, _cfg(), tmp_cache, k=3)
        assert answer == "answer" and papers == [paper]
        messages = mock_llm.call_args.args[0]
        assert [m["content"] for m in messages[:-1]] == ["q2", "a2", "q3", "a3", "q4", "a4"]
        assert messages[-1]["role"] == "user"
        assert "follow-up?" in messages[-1]["content"]
        assert "alpha abstract" in messages[-1]["content"]

    def test_history_is_normalised(self):
        history = [
            {"role": "assistant", "content": "stray greeting"},
            {"role": "user", "content": "q1"},
            {"role": "user", "content": "q1 again"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "ignored"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "unanswered"},
        ]
        assert _history_messages(history) == [
            {"role": "user", "content": "q1\n\nq1 again"},
            {"role": "assistant", "content": "a1"},
        ]
        assert _history_messages(None) == []

    def test_call_llm_anthropic_messages_payload(self):
        cfg = {"llm": {"provider": "anthropic", "api_key": "k", "model": "claude-x"}}
        resp = MagicMock()
        resp.json.return_value = {"content": [{"text": "hi"}]}
        messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        with patch("httpx.post", return_value=resp) as mock_post:
            assert _call_llm(messages, cfg, max_tokens=123) == "hi"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["messages"] == messages
        assert payload["max_tokens"] == 123

    def test_call_llm_http_error_is_runtime_error(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(
            401, request=request, json={"error": {"message": "Incorrect API key provided"}}
        )
        with patch("httpx.post", return_value=response):
            with pytest.raises(RuntimeError, match=r"HTTP 401.*Incorrect API key"):
                _call_llm("hello", _cfg())

    def test_call_llm_timeout_is_runtime_error(self):
        with patch("httpx.post", side_effect=httpx.ReadTimeout("slow")):
            with pytest.raises(RuntimeError, match="could not reach"):
                _call_llm("hello", _cfg())

    def test_call_llm_unexpected_body(self):
        resp = MagicMock()
        resp.json.return_value = {"unexpected": True}
        with patch("httpx.post", return_value=resp):
            with pytest.raises(RuntimeError, match="unexpected response"):
                _call_llm("hello", _cfg())


class TestBuildContextCaps:
    def test_excerpt_used_with_abstract_snippet(self):
        paper = _p("Alpha", "short abstract")
        ctx = _build_context([paper], {f"{paper.uid}::3": "matched passage"})
        assert "Abstract: short abstract" in ctx
        assert "Excerpt: matched passage" in ctx

    def test_total_context_is_bounded(self):
        from mosaic.rag import _CONTEXT_MAX_CHARS

        papers = [_p(f"P{i}", "a" * 1000) for i in range(50)]
        chunks = {f"{p.uid}::0": "x" * 3000 for p in papers}
        ctx = _build_context(papers, chunks)
        header_allowance = 200 * len(papers)
        assert len(ctx) < _CONTEXT_MAX_CHARS + header_allowance
        assert ctx.count("[50]") == 1  # every paper still present
