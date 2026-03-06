"""Tests for Paper and SearchFilters models."""
import pytest
from mosaic.models import Paper, SearchFilters


# ── SearchFilters.parse_year ─────────────────────────────────────────────────

class TestParseYear:
    def test_single_year(self):
        f = SearchFilters.parse_year("2020")
        assert f.year_from == 2020
        assert f.year_to == 2020
        assert f.years is None

    def test_range(self):
        f = SearchFilters.parse_year("2018-2022")
        assert f.year_from == 2018
        assert f.year_to == 2022
        assert f.years is None

    def test_list(self):
        f = SearchFilters.parse_year("2019,2021,2023")
        assert f.years == [2019, 2021, 2023]
        assert f.year_from is None
        assert f.year_to is None

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            SearchFilters.parse_year("abc")


# ── SearchFilters.match ──────────────────────────────────────────────────────

class TestMatch:
    def _paper(self, year=2020, authors=None, journal="Nature"):
        return Paper(
            title="T", year=year,
            authors=authors or ["Alice Smith"],
            journal=journal,
        )

    def test_no_filters_always_matches(self):
        assert SearchFilters().match(self._paper())

    def test_year_inside_range(self):
        f = SearchFilters(year_from=2018, year_to=2022)
        assert f.match(self._paper(year=2020))

    def test_year_below_range(self):
        f = SearchFilters(year_from=2018, year_to=2022)
        assert not f.match(self._paper(year=2015))

    def test_year_above_range(self):
        f = SearchFilters(year_from=2018, year_to=2022)
        assert not f.match(self._paper(year=2024))

    def test_year_in_explicit_list(self):
        f = SearchFilters(years=[2019, 2021])
        assert f.match(self._paper(year=2021))

    def test_year_not_in_explicit_list(self):
        f = SearchFilters(years=[2019, 2021])
        assert not f.match(self._paper(year=2020))

    def test_paper_without_year_skips_year_check(self):
        f = SearchFilters(year_from=2020, year_to=2022)
        assert f.match(Paper(title="T", authors=[], year=None))

    def test_author_substring_match(self):
        f = SearchFilters(authors=["Smith"])
        assert f.match(self._paper(authors=["Alice Smith"]))

    def test_author_case_insensitive(self):
        f = SearchFilters(authors=["smith"])
        assert f.match(self._paper(authors=["Alice Smith"]))

    def test_author_no_match(self):
        f = SearchFilters(authors=["Jones"])
        assert not f.match(self._paper(authors=["Alice Smith"]))

    def test_multiple_authors_or_logic(self):
        f = SearchFilters(authors=["Jones", "Smith"])
        assert f.match(self._paper(authors=["Alice Smith"]))

    def test_journal_substring_match(self):
        f = SearchFilters(journal="nature")
        assert f.match(self._paper(journal="Nature Communications"))

    def test_journal_no_match(self):
        f = SearchFilters(journal="Science")
        assert not f.match(self._paper(journal="Nature"))

    def test_journal_missing_on_paper(self):
        f = SearchFilters(journal="Nature")
        assert not f.match(Paper(title="T", authors=[], journal=None))

    def test_combined_filters_all_must_match(self):
        f = SearchFilters(year_from=2017, year_to=2017, authors=["Vaswani"])
        good = Paper(title="T", authors=["Ashish Vaswani"], year=2017)
        wrong_year = Paper(title="T", authors=["Ashish Vaswani"], year=2019)
        wrong_author = Paper(title="T", authors=["John Doe"], year=2017)
        assert f.match(good)
        assert not f.match(wrong_year)
        assert not f.match(wrong_author)


# ── Paper properties ─────────────────────────────────────────────────────────

class TestPaperUid:
    def test_doi_preferred(self):
        p = Paper(title="T", doi="10.1234/test", arxiv_id="1234.5678")
        assert p.uid.startswith("doi:")

    def test_arxiv_fallback(self):
        p = Paper(title="T", arxiv_id="1234.5678")
        assert p.uid == "arxiv:1234.5678"

    def test_pii_fallback(self):
        p = Paper(title="T", pii="S0000")
        assert p.uid == "pii:S0000"

    def test_title_last_resort(self):
        p = Paper(title="Some Paper")
        assert p.uid.startswith("title:")

    def test_doi_normalised_lowercase(self):
        p = Paper(title="T", doi="10.1234/TEST")
        assert p.uid == "doi:10.1234/test"

    def test_arxiv_doi_normalised_to_arxiv_prefix(self):
        # Ensures arXiv papers from OpenAlex (doi=10.48550/arxiv.XXXX) and
        # from arXiv directly (arxiv_id=XXXX) produce the same uid.
        p_openalex = Paper(title="T", doi="10.48550/arXiv.2501.12345")
        p_arxiv    = Paper(title="T", arxiv_id="2501.12345")
        assert p_openalex.uid == "arxiv:2501.12345"
        assert p_arxiv.uid    == "arxiv:2501.12345"


class TestPaperShortAuthors:
    def test_no_authors(self):
        assert Paper(title="T").short_authors == "Unknown"

    def test_one_author(self):
        assert Paper(title="T", authors=["Alice"]).short_authors == "Alice"

    def test_two_authors(self):
        assert Paper(title="T", authors=["Alice", "Bob"]).short_authors == "Alice & Bob"

    def test_three_plus_authors(self):
        assert Paper(title="T", authors=["Alice", "Bob", "Carol"]).short_authors == "Alice et al."


class TestPaperSafeFilename:
    def test_contains_author_year_title(self):
        # safe_filename uses the first word of the first author's name
        p = Paper(title="Deep Learning", authors=["Yann LeCun"], year=2015)
        fn = p.safe_filename()
        assert "Yann" in fn
        assert "2015" in fn
        assert "Deep_Learning" in fn
        assert fn.endswith(".pdf")

    def test_special_chars_stripped(self):
        p = Paper(title="A: B? C!", authors=["Smith"], year=2020)
        fn = p.safe_filename()
        assert ":" not in fn
        assert "?" not in fn
        assert "!" not in fn
