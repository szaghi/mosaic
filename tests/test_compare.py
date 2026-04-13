"""Tests for mosaic/compare.py — LLM extraction and output formatters."""

import json
from unittest.mock import patch

import pytest

from mosaic.compare import (
    DEFAULT_DIMENSIONS,
    _metadata_fallback,
    _parse_obj_list,
    compare_papers,
    format_csv,
    format_json_output,
    format_markdown,
)
from mosaic.models import Paper

# ── helpers ───────────────────────────────────────────────────────────────────


def _paper(
    title: str,
    abstract: str = "",
    year: int = 2020,
    doi: str | None = None,
    journal: str | None = None,
    citation_count: int | None = None,
) -> Paper:
    return Paper(
        title=title,
        abstract=abstract,
        year=year,
        doi=doi,
        journal=journal,
        citation_count=citation_count,
        authors=["Author A", "Author B"],
        source="test",
    )


# ── _metadata_fallback ────────────────────────────────────────────────────────


class TestMetadataFallback:
    def test_year_extracted(self):
        papers = [_paper("T", year=2022)]
        rows = _metadata_fallback(papers, ["year"])
        assert rows[0]["year"] == "2022"

    def test_missing_year_returns_dash(self):
        p = Paper(title="T", source="test")
        rows = _metadata_fallback([p], ["year"])
        assert rows[0]["year"] == "–"

    def test_journal_extracted(self):
        papers = [_paper("T", journal="Nature")]
        rows = _metadata_fallback(papers, ["journal"])
        assert rows[0]["journal"] == "Nature"

    def test_doi_extracted(self):
        papers = [_paper("T", doi="10.1234/x")]
        rows = _metadata_fallback(papers, ["doi"])
        assert rows[0]["doi"] == "10.1234/x"

    def test_source_extracted(self):
        papers = [_paper("T")]
        rows = _metadata_fallback(papers, ["source"])
        assert rows[0]["source"] == "test"

    def test_citation_count_variants(self):
        papers = [_paper("T", citation_count=42)]
        for dim in ("citations", "citation_count", "cited"):
            rows = _metadata_fallback(papers, [dim])
            assert rows[0][dim] == "42"

    def test_llm_dimension_returns_dash(self):
        papers = [_paper("T")]
        rows = _metadata_fallback(papers, ["method"])
        assert rows[0]["method"] == "–"

    def test_multiple_papers(self):
        papers = [_paper("A", year=2021), _paper("B", year=2022)]
        rows = _metadata_fallback(papers, ["year"])
        assert rows[0]["year"] == "2021"
        assert rows[1]["year"] == "2022"

    def test_multiple_dimensions(self):
        papers = [_paper("T", year=2020, doi="10.1/x")]
        rows = _metadata_fallback(papers, ["year", "doi"])
        assert rows[0]["year"] == "2020"
        assert rows[0]["doi"] == "10.1/x"


# ── _parse_obj_list ───────────────────────────────────────────────────────────


class TestParseObjList:
    def test_plain_array(self):
        content = '[{"method": "CNN", "dataset": "ImageNet"}]'
        rows = _parse_obj_list(content, 1, ["method", "dataset"])
        assert rows[0]["method"] == "CNN"
        assert rows[0]["dataset"] == "ImageNet"

    def test_dict_wrapper_unwrapped(self):
        content = '{"papers": [{"method": "SVM"}]}'
        rows = _parse_obj_list(content, 1, ["method"])
        assert rows[0]["method"] == "SVM"

    def test_missing_key_defaults_to_dash(self):
        content = '[{"method": "CNN"}]'
        rows = _parse_obj_list(content, 1, ["method", "dataset"])
        assert rows[0]["dataset"] == "–"

    def test_padded_when_shorter_than_expected(self):
        content = '[{"method": "CNN"}]'
        rows = _parse_obj_list(content, 3, ["method"])
        assert len(rows) == 3
        assert rows[1]["method"] == "–"

    def test_truncated_when_longer_than_expected(self):
        content = '[{"method": "A"}, {"method": "B"}, {"method": "C"}]'
        rows = _parse_obj_list(content, 2, ["method"])
        assert len(rows) == 2

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="non-JSON"):
            _parse_obj_list("not json", 1, ["method"])

    def test_dict_without_list_raises(self):
        with pytest.raises(ValueError, match="No array found"):
            _parse_obj_list('{"a": 1, "b": 2}', 1, ["method"])

    def test_wrong_type_raises(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            _parse_obj_list('"just a string"', 1, ["method"])

    def test_non_dict_item_returns_dash_row(self):
        content = '["not an object"]'
        rows = _parse_obj_list(content, 1, ["method"])
        assert rows[0]["method"] == "–"


# ── compare_papers ────────────────────────────────────────────────────────────


class TestComparePapers:
    def test_no_llm_uses_metadata(self):
        papers = [_paper("T", year=2021)]
        rows = compare_papers(papers, ["year"], cfg={})
        assert rows[0]["year"] == "2021"

    def test_llm_called_when_configured(self):
        papers = [_paper("T", abstract="uses Transformer on CIFAR-10")]
        cfg = {"llm": {"provider": "openai", "api_key": "sk-fake", "model": "gpt-4o-mini"}}
        fake_response = '[{"method": "Transformer", "dataset": "CIFAR-10"}]'
        with patch("mosaic.compare._call_llm", return_value=fake_response):
            rows = compare_papers(papers, ["method", "dataset"], cfg)
        assert rows[0]["method"] == "Transformer"
        assert rows[0]["dataset"] == "CIFAR-10"

    def test_llm_failure_falls_back_to_metadata(self):
        papers = [_paper("T", year=2022)]
        cfg = {"llm": {"provider": "openai", "api_key": "sk-fake"}}
        with patch("mosaic.compare._llm_extract", side_effect=RuntimeError("network error")):
            rows = compare_papers(papers, ["year"], cfg)
        assert rows[0]["year"] == "2022"

    def test_empty_papers_returns_empty(self):
        rows = compare_papers([], ["method"], cfg={})
        assert rows == []

    def test_default_dimensions_constant(self):
        assert DEFAULT_DIMENSIONS == ["method", "dataset", "metric", "result"]


# ── format_markdown ───────────────────────────────────────────────────────────


class TestFormatMarkdown:
    def test_header_row_present(self):
        papers = [_paper("A Paper", year=2020)]
        rows = [{"method": "CNN"}]
        out = format_markdown(papers, rows, ["method"])
        lines = out.splitlines()
        assert "Title" in lines[0]
        assert "Method" in lines[0]

    def test_separator_row_present(self):
        papers = [_paper("A")]
        rows = [{"method": "SVM"}]
        out = format_markdown(papers, rows, ["method"])
        lines = out.splitlines()
        assert "---" in lines[1]

    def test_data_row_contains_title(self):
        papers = [_paper("My Cool Paper", year=2021)]
        rows = [{"method": "GAN"}]
        out = format_markdown(papers, rows, ["method"])
        assert "My Cool Paper" in out

    def test_pipe_in_title_escaped(self):
        papers = [_paper("Title | With Pipe", year=2020)]
        rows = [{"method": "–"}]
        out = format_markdown(papers, rows, ["method"])
        # The raw pipe in the title must be escaped so the table stays valid
        data_line = out.splitlines()[2]
        # Count non-escaped pipes — should be exactly the table column separators
        assert "Title \\| With Pipe" in data_line

    def test_row_count_matches_papers(self):
        papers = [_paper(f"P{i}", year=2020 + i) for i in range(5)]
        rows = [{"method": "–"} for _ in papers]
        out = format_markdown(papers, rows, ["method"])
        # header + separator + 5 data rows = 7 lines
        assert len(out.splitlines()) == 7


# ── format_csv ────────────────────────────────────────────────────────────────


class TestFormatCsv:
    def test_header_present(self):
        papers = [_paper("T")]
        rows = [{"method": "CNN"}]
        out = format_csv(papers, rows, ["method"])
        first_line = out.splitlines()[0]
        assert "title" in first_line
        assert "method" in first_line

    def test_data_row_present(self):
        papers = [_paper("My Paper", year=2021)]
        rows = [{"method": "GAN"}]
        out = format_csv(papers, rows, ["method"])
        assert "My Paper" in out
        assert "GAN" in out

    def test_row_count(self):
        papers = [_paper(f"P{i}") for i in range(3)]
        rows = [{"method": "–"} for _ in papers]
        out = format_csv(papers, rows, ["method"])
        # header + 3 data rows
        assert len(out.strip().splitlines()) == 4


# ── format_json_output ────────────────────────────────────────────────────────


class TestFormatJsonOutput:
    def test_valid_json(self):
        papers = [_paper("T", doi="10.1/x", year=2020)]
        rows = [{"method": "CNN"}]
        out = format_json_output(papers, rows, ["method"])
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_entry_fields(self):
        papers = [_paper("T", doi="10.1/x", year=2020)]
        rows = [{"method": "CNN", "dataset": "CIFAR"}]
        data = json.loads(format_json_output(papers, rows, ["method", "dataset"]))
        entry = data[0]
        assert entry["title"] == "T"
        assert entry["year"] == 2020
        assert entry["doi"] == "10.1/x"
        assert entry["method"] == "CNN"
        assert entry["dataset"] == "CIFAR"

    def test_numbering_starts_at_one(self):
        papers = [_paper("A"), _paper("B")]
        rows = [{"method": "–"}, {"method": "–"}]
        data = json.loads(format_json_output(papers, rows, ["method"]))
        assert data[0]["#"] == 1
        assert data[1]["#"] == 2
