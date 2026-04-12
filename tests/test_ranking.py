"""Tests for mosaic/ranking.py and services.sort_by_relevance."""

from unittest.mock import patch

import pytest

from mosaic.models import Paper
from mosaic.ranking import _bm25_score, _parse_float_list, score_papers
from mosaic.services import sort_by_relevance

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _paper(title: str, abstract: str = "", year: int = 2020) -> Paper:
    return Paper(title=title, abstract=abstract, year=year, source="test")


# ---------------------------------------------------------------------------
# _bm25_score
# ---------------------------------------------------------------------------


class TestBm25Score:
    def test_relevant_paper_scores_higher(self):
        """A paper whose abstract matches the query should outrank one that does not."""
        p_relevant = _paper(
            "Neural Networks", abstract="deep learning transformer attention mechanism"
        )
        p_unrelated = _paper("Cooking Pasta", abstract="boil water add pasta stir")
        papers = [p_relevant, p_unrelated]
        _bm25_score("transformer attention", papers)
        assert p_relevant.relevance_score > p_unrelated.relevance_score

    def test_top_score_is_one(self):
        """The most relevant paper should have relevance_score == 1.0."""
        papers = [
            _paper("A", abstract="transformer attention mechanism"),
            _paper("B", abstract="unrelated content"),
        ]
        _bm25_score("transformer attention", papers)
        assert max(p.relevance_score for p in papers) == pytest.approx(1.0)

    def test_no_abstract_scores_lower_than_matching_paper(self):
        """A paper with no content should score lower than one matching the query."""
        p_empty = Paper(title="", abstract=None, source="test")
        p_match = _paper("Transformers", abstract="attention is all you need")
        papers = [p_empty, p_match]
        _bm25_score("attention transformer", papers)
        assert p_match.relevance_score > p_empty.relevance_score

    def test_all_zero_bm25_scores(self):
        """When no token matches, all scores are 0.0 and no ZeroDivisionError occurs."""
        papers = [_paper("Alpha"), _paper("Beta")]
        _bm25_score("zzzznotaword", papers)
        for p in papers:
            assert p.relevance_score == pytest.approx(0.0)

    def test_single_paper(self):
        """A single paper should score 1.0 if it matches (max normalisation)."""
        papers = [_paper("Attention Mechanism", abstract="self-attention transformer")]
        _bm25_score("attention", papers)
        assert papers[0].relevance_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _parse_float_list
# ---------------------------------------------------------------------------


class TestParseFloatList:
    def test_plain_list(self):
        result = _parse_float_list("[0.9, 0.3, 0.7]", 3)
        assert result == pytest.approx([0.9, 0.3, 0.7])

    def test_dict_with_list_value(self):
        result = _parse_float_list('{"scores": [0.8, 0.2]}', 2)
        assert result == pytest.approx([0.8, 0.2])

    def test_pads_short_response(self):
        result = _parse_float_list("[0.5]", 3)
        assert len(result) == 3
        assert result[1] == pytest.approx(0.5)  # padded with 0.5

    def test_truncates_long_response(self):
        result = _parse_float_list("[0.1, 0.2, 0.3, 0.4]", 2)
        assert result == pytest.approx([0.1, 0.2])

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="non-JSON"):
            _parse_float_list("not json", 2)

    def test_dict_without_list_raises(self):
        with pytest.raises(ValueError, match="No list found"):
            _parse_float_list('{"a": 1}', 2)


# ---------------------------------------------------------------------------
# score_papers
# ---------------------------------------------------------------------------


class TestScorePapers:
    def test_empty_query_returns_unchanged(self):
        papers = [_paper("Test")]
        result = score_papers("", papers, {})
        assert result[0].relevance_score is None

    def test_empty_papers_returns_empty(self):
        result = score_papers("query", [], {})
        assert result == []

    def test_bm25_used_when_no_llm_config(self):
        papers = [_paper("Transformers", abstract="attention"), _paper("Food", abstract="pasta")]
        result = score_papers("attention transformer", papers, {})
        assert all(p.relevance_score is not None for p in result)

    def test_llm_fallback_to_bm25_on_failure(self):
        """When LLM scoring raises, BM25 should be used as fallback."""
        papers = [_paper("Transformers", abstract="attention")]
        cfg = {"llm": {"provider": "openai", "api_key": "sk-fake", "model": "gpt-4o-mini"}}
        with patch("mosaic.ranking._llm_score", side_effect=RuntimeError("network error")):
            result = score_papers("attention", papers, cfg)
        assert result[0].relevance_score is not None


# ---------------------------------------------------------------------------
# sort_by_relevance (services integration)
# ---------------------------------------------------------------------------


class TestSortByRelevance:
    def test_orders_by_relevance_descending(self):
        papers = [
            _paper("Cooking", abstract="pasta water salt"),
            _paper("AI", abstract="transformer attention neural network deep learning"),
        ]
        cfg = {}
        result = sort_by_relevance("transformer attention neural", papers, cfg)
        assert result[0].title == "AI"
        assert result[0].relevance_score >= result[1].relevance_score

    def test_returns_all_papers(self):
        papers = [_paper(f"Paper {i}") for i in range(5)]
        result = sort_by_relevance("neural network", papers, {})
        assert len(result) == 5

    def test_scores_set_on_all_papers(self):
        papers = [_paper("A", abstract="test"), _paper("B", abstract="other")]
        result = sort_by_relevance("test", papers, {})
        assert all(p.relevance_score is not None for p in result)
