"""Author-filter matching, blank author names and DOI extraction from bulk files."""

from __future__ import annotations

from pathlib import Path

import pytest

from mosaic.bulk import read_dois
from mosaic.models import Paper, SearchFilters


def _match(filter_name: str, *authors: str) -> bool:
    return SearchFilters(authors=[filter_name]).match(Paper(title="T", authors=list(authors)))


class TestAuthorMatching:
    @pytest.mark.parametrize(
        "author",
        [
            "Hinton GE",  # PubMed / PMC
            "Hinton, Geoffrey",  # Crossref, Springer
            "Hinton, G. E.",  # NASA ADS
            "Geoffrey E. Hinton",
            "GEOFFREY HINTON",
            "Geoffrey Hinton",
        ],
    )
    def test_full_name_matches_source_formats(self, author):
        assert _match("Geoffrey Hinton", author)

    @pytest.mark.parametrize("author", ["Hinton, Alice", "Alice Hinton", "Hinton A", "G. Hintonen"])
    def test_different_person_rejected(self, author):
        assert not _match("Geoffrey Hinton", author)

    def test_initial_filter_matches_full_given_name(self):
        assert _match("G. Hinton", "Geoffrey Hinton")

    def test_filter_in_family_given_form(self):
        assert _match("Hinton, Geoffrey", "Geoffrey E. Hinton")

    def test_surname_only_filter(self):
        assert _match("hinton", "Hinton GE")

    def test_partial_substring_still_matches(self):
        # Backwards compatible with the old substring filter
        assert _match("Hint", "Geoffrey Hinton")

    def test_accents_ignored(self):
        assert _match("Jurgen Muller", "Jürgen Müller")

    def test_chinese_given_family_not_confused(self):
        assert _match("Li Wei", "Wei Li")
        assert not _match("Li Wei", "Wei Liu")

    def test_or_across_multiple_filter_authors(self):
        f = SearchFilters(authors=["Yann LeCun", "Geoffrey Hinton"])
        assert f.match(Paper(title="T", authors=["Hinton GE"]))
        assert f.match(Paper(title="T", authors=["LeCun, Yann"]))
        assert not f.match(Paper(title="T", authors=["Bengio Y"]))

    def test_none_author_entries_do_not_crash(self):
        p = Paper(title="T", authors=[None, "A B"])  # type: ignore[list-item]
        assert SearchFilters(authors=["A B"]).match(p)

    def test_papers_without_year_still_pass_year_filter(self):
        # Unchanged behaviour: unknown years are not filtered out
        assert SearchFilters(year_from=2020, year_to=2020).match(Paper(title="T"))


class TestSafeFilenameBlankAuthors:
    def test_empty_author_string(self):
        assert Paper(title="T", authors=[""], year=2020).safe_filename() == "2020__Unknown_T.pdf"

    def test_whitespace_author(self):
        assert "Unknown" in Paper(title="T", authors=["   "]).safe_filename()

    def test_first_blank_uses_next_author(self):
        assert "_Bob_" in Paper(title="T", authors=["", "Bob Smith"]).safe_filename()

    def test_normal_names_unchanged(self):
        p = Paper(title="Title", authors=["Wei Zhang", "Li"], year=2020, source="arXiv")
        assert p.safe_filename() == "2020_arXiv_Wei_Title.pdf"


class TestBulkDoiNormalisation:
    def _write(self, tmp_path: Path, name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_bib_keeps_url_form_dois(self, tmp_path):
        f = self._write(
            tmp_path,
            "r.bib",
            "@article{a, doi = {https://doi.org/10.1234/abc}}\n"
            '@article{b, doi = "http://dx.doi.org/10.1234/def"}\n',
        )
        assert read_dois(f) == ["10.1234/abc", "10.1234/def"]

    def test_csv_strips_prefixes(self, tmp_path):
        f = self._write(
            tmp_path,
            "r.csv",
            "doi\nhttps://doi.org/10.1234/abc\ndoi:10.1234/def\nHTTPS://DX.DOI.ORG/10.1234/ghi\n",
        )
        assert read_dois(f) == ["10.1234/abc", "10.1234/def", "10.1234/ghi"]

    def test_case_insensitive_dedupe(self, tmp_path):
        f = self._write(
            tmp_path, "r.csv", "doi\n10.1234/ABC\n10.1234/abc\nhttps://doi.org/10.1234/Abc\n"
        )
        assert read_dois(f) == ["10.1234/ABC"]

    def test_csv_skips_non_doi_values(self, tmp_path):
        f = self._write(tmp_path, "r.csv", "doi\nN/A\n10.1234/ok\n-\n")
        assert read_dois(f) == ["10.1234/ok"]

    def test_bib_and_csv_agree(self, tmp_path):
        bib = self._write(tmp_path, "r.bib", "@article{a, doi = {https://doi.org/10.5555/X}}")
        csv = self._write(tmp_path, "r.csv", "doi\nhttps://doi.org/10.5555/X\n")
        assert read_dois(bib) == read_dois(csv) == ["10.5555/X"]
