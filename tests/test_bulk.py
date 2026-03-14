"""Tests for mosaic.bulk — DOI extraction from BibTeX and CSV files."""

from pathlib import Path

import pytest

from mosaic.bulk import _read_bib, _read_csv, read_dois

# ── helpers ───────────────────────────────────────────────────────────────────


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ── read_dois dispatcher ──────────────────────────────────────────────────────


class TestReadDois:
    def test_dispatches_bib(self, tmp_path):
        f = write(tmp_path, "refs.bib", "@article{x, doi = {10.1/test}}")
        assert read_dois(f) == ["10.1/test"]

    def test_dispatches_csv(self, tmp_path):
        f = write(tmp_path, "refs.csv", "doi\n10.1/test\n")
        assert read_dois(f) == ["10.1/test"]

    def test_raises_on_unsupported_extension(self, tmp_path):
        f = write(tmp_path, "refs.txt", "")
        with pytest.raises(ValueError, match="Unsupported file type"):
            read_dois(f)

    def test_extension_case_insensitive(self, tmp_path):
        f = write(tmp_path, "refs.BIB", "@article{x, doi = {10.1/test}}")
        assert read_dois(f) == ["10.1/test"]


# ── _read_bib ─────────────────────────────────────────────────────────────────


class TestReadBib:
    def test_extracts_doi_curly_braces(self, tmp_path):
        f = write(tmp_path, "r.bib", "@article{key, doi = {10.1234/test}}")
        assert _read_bib(f) == ["10.1234/test"]

    def test_extracts_doi_double_quotes(self, tmp_path):
        f = write(tmp_path, "r.bib", '@article{key, doi = "10.1234/test"}')
        assert _read_bib(f) == ["10.1234/test"]

    def test_case_insensitive_key(self, tmp_path):
        f = write(tmp_path, "r.bib", "@article{key, DOI = {10.1/x}}")
        assert _read_bib(f) == ["10.1/x"]

    def test_multiple_entries(self, tmp_path):
        content = "@article{a, doi = {10.1/aaa}}\n@article{b, doi = {10.1/bbb}}\n"
        f = write(tmp_path, "r.bib", content)
        assert _read_bib(f) == ["10.1/aaa", "10.1/bbb"]

    def test_deduplicates(self, tmp_path):
        content = "@article{a, doi = {10.1/dup}}\n@article{b, doi = {10.1/dup}}\n"
        f = write(tmp_path, "r.bib", content)
        assert _read_bib(f) == ["10.1/dup"]

    def test_empty_file_returns_empty(self, tmp_path):
        f = write(tmp_path, "r.bib", "")
        assert _read_bib(f) == []

    def test_no_doi_fields_returns_empty(self, tmp_path):
        f = write(tmp_path, "r.bib", "@article{x, title = {No DOI here}}")
        assert _read_bib(f) == []

    def test_doi_with_slashes_and_dots(self, tmp_path):
        doi = "10.48550/arXiv.1706.03762"
        f = write(tmp_path, "r.bib", f"@misc{{x, doi = {{{doi}}}}}")
        assert _read_bib(f) == [doi]

    def test_whitespace_around_value(self, tmp_path):
        f = write(tmp_path, "r.bib", "@article{x, doi = {  10.1/abc  }}")
        result = _read_bib(f)
        assert result == ["10.1/abc"]

    def test_preserves_order(self, tmp_path):
        content = "\n".join(f"@article{{e{i}, doi = {{10.1/{i}}}}}" for i in range(5))
        f = write(tmp_path, "r.bib", content)
        assert _read_bib(f) == [f"10.1/{i}" for i in range(5)]


# ── _read_csv ─────────────────────────────────────────────────────────────────


class TestReadCsv:
    def test_reads_doi_column(self, tmp_path):
        f = write(tmp_path, "r.csv", "doi\n10.1/test\n")
        assert _read_csv(f) == ["10.1/test"]

    def test_case_insensitive_header(self, tmp_path):
        f = write(tmp_path, "r.csv", "DOI\n10.1/test\n")
        assert _read_csv(f) == ["10.1/test"]

    def test_extra_columns_ignored(self, tmp_path):
        f = write(tmp_path, "r.csv", "title,doi,year\nTest,10.1/t,2020\n")
        assert _read_csv(f) == ["10.1/t"]

    def test_deduplicates(self, tmp_path):
        f = write(tmp_path, "r.csv", "doi\n10.1/dup\n10.1/dup\n")
        assert _read_csv(f) == ["10.1/dup"]

    def test_skips_empty_doi_cells(self, tmp_path):
        f = write(tmp_path, "r.csv", "doi\n10.1/ok\n\n10.1/also\n")
        assert _read_csv(f) == ["10.1/ok", "10.1/also"]

    def test_empty_file_returns_empty(self, tmp_path):
        f = write(tmp_path, "r.csv", "doi\n")
        assert _read_csv(f) == []

    def test_raises_when_no_doi_column(self, tmp_path):
        f = write(tmp_path, "r.csv", "title,year\nFoo,2020\n")
        with pytest.raises(ValueError, match="no 'doi' column"):
            _read_csv(f)

    def test_preserves_order(self, tmp_path):
        rows = "\n".join(f"10.1/{i}" for i in range(5))
        f = write(tmp_path, "r.csv", f"doi\n{rows}\n")
        assert _read_csv(f) == [f"10.1/{i}" for i in range(5)]

    def test_strips_whitespace_from_values(self, tmp_path):
        f = write(tmp_path, "r.csv", "doi\n  10.1/ws  \n")
        assert _read_csv(f) == ["10.1/ws"]
