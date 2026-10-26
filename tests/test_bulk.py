"""Tests for mosaic.bulk — DOI extraction from BibTeX and CSV files."""

from pathlib import Path
from unittest.mock import patch

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


class TestFailedListPrompt:
    """`mosaic get --from` asks whether to save the still-failing DOIs in a CSV."""

    def _invoke(self, monkeypatch, tmp_path, dois, confirm_return=True, isatty=False):
        from typer.testing import CliRunner

        from mosaic.cli import app
        from mosaic.models import Paper

        monkeypatch.chdir(tmp_path)
        source = tmp_path / "missing.csv"
        source.write_text("doi\n" + "\n".join(dois) + "\n")
        cfg = {
            "db_path": ":memory:",
            "download_dir": str(tmp_path / "dl"),
            "unpaywall": {"email": ""},
        }
        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.Cache"),
            patch(
                "mosaic.cite.paper_for_download",
                side_effect=lambda d, *a: Paper(title=f"T {d}", doi=d, year=2018),
            ),
            patch("mosaic.cli.dl_paper", return_value=None),
            patch("mosaic.cli.typer.confirm", return_value=confirm_return) as ask,
            patch("mosaic.cli._stdin_isatty", return_value=isatty),
        ):
            r = CliRunner().invoke(app, ["get", "--from", str(source)])
        return r, ask

    def test_prompt_is_skipped_when_not_a_tty(self, monkeypatch, tmp_path):
        r, ask = self._invoke(monkeypatch, tmp_path, ["10.1/a"])
        assert r.exit_code == 1, r.output  # papers still failed
        ask.assert_not_called()
        assert not (tmp_path / "missing-failed.csv").exists()

    def test_accept_writes_csv_feedable_to_from(self, monkeypatch, tmp_path):
        from mosaic.bulk import read_dois

        r, ask = self._invoke(monkeypatch, tmp_path, ["10.1/a", "10.1/b"], isatty=True)
        assert r.exit_code == 1, r.output
        out = tmp_path / "missing-failed.csv"
        assert ask.called and out.exists()
        assert read_dois(out) == ["10.1/a", "10.1/b"]

    def test_decline_writes_nothing(self, monkeypatch, tmp_path):
        r, ask = self._invoke(monkeypatch, tmp_path, ["10.1/a"], confirm_return=False, isatty=True)
        assert r.exit_code == 1, r.output
        assert ask.called
        assert not (tmp_path / "missing-failed.csv").exists()

    def test_none_saved_when_all_download(self, monkeypatch, tmp_path):
        from typer.testing import CliRunner

        from mosaic.cli import app
        from mosaic.models import Paper

        monkeypatch.chdir(tmp_path)
        source = tmp_path / "ok.csv"
        source.write_text("doi\n10.1/a\n")
        cfg = {
            "db_path": ":memory:",
            "download_dir": str(tmp_path / "dl"),
            "unpaywall": {"email": ""},
        }
        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.Cache"),
            patch(
                "mosaic.cite.paper_for_download",
                side_effect=lambda d, *a: Paper(title=f"T {d}", doi=d, year=2018),
            ),
            patch("mosaic.cli.dl_paper", return_value=str(tmp_path / "dl" / "x.pdf")),
        ):
            r = CliRunner().invoke(app, ["get", "--from", str(source)])
        assert r.exit_code == 0, r.output


class TestFailedCsvPath:
    def test_versions_when_the_suggested_name_exists(self, monkeypatch, tmp_path):
        from mosaic.cli import _failed_csv_path

        monkeypatch.chdir(tmp_path)
        (tmp_path / "refs-failed.csv").write_text("doi\n", encoding="utf-8")
        (tmp_path / "refs-failed-2.csv").write_text("doi\n", encoding="utf-8")
        assert _failed_csv_path(Path("refs.bib")) == Path("refs-failed-3.csv")
        assert _failed_csv_path(None) == Path("failed.csv")
