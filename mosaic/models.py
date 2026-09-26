"""Unified paper data model."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def _name_tokens(name: str) -> list[str]:
    """Lower-case, accent-free word tokens of a person name.

    Run-together initials as PubMed writes them are split into single
    letters: ``"Hinton GE"`` → ``["hinton", "g", "e"]``, and
    ``"Hinton, G. E."`` gives the same tokens.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens: list[str] = []
    for raw in re.split(r"[^\w]+", ascii_name):
        if not raw:
            continue
        if 2 <= len(raw) <= 3 and raw.isalpha() and raw.isupper():
            tokens.extend(raw.lower())
        else:
            tokens.append(raw.lower())
    return tokens


def _given_compatible(filter_token: str, author_token: str) -> bool:
    """True if two given-name tokens can denote the same person (name or initial)."""
    if filter_token == author_token:
        return True
    if len(filter_token) == 1 or len(author_token) == 1:
        return filter_token[0] == author_token[0]
    return False


def _author_name_matches(filter_name: str, author: str) -> bool:
    """Token-based match of one filter name against one author name.

    One filter token must equal an author token (the surname); every other
    filter token must be compatible with a distinct remaining author token.
    Name order, commas, periods, case and accents are ignored, so
    "Geoffrey Hinton" matches "Hinton GE", "Hinton, G. E." and
    "Geoffrey E. Hinton".
    """
    f_tokens = _name_tokens(filter_name)
    a_tokens = _name_tokens(author)
    if not f_tokens or not a_tokens:
        return False
    for i, surname in enumerate(f_tokens):
        if len(surname) < 2 or surname not in a_tokens:
            continue
        remaining = list(a_tokens)
        remaining.remove(surname)
        if not remaining:
            return True  # author recorded by surname only
        ok = True
        for given in f_tokens[:i] + f_tokens[i + 1 :]:
            match = next((t for t in remaining if _given_compatible(given, t)), None)
            if match is None:
                ok = False
                break
            remaining.remove(match)
        if ok:
            return True
    return False


def _author_matches(filter_name: str, authors: list[str]) -> bool:
    """True if *filter_name* matches any of *authors*.

    The historical case-insensitive substring match is kept (so partial names
    such as "Hint" still work); token matching is tried on top of it.
    """
    needle = filter_name.lower()
    if needle and needle in " ".join(authors).lower():
        return True
    return any(_author_name_matches(filter_name, a) for a in authors)


@dataclass
class SearchFilters:
    """Filters applied both at the API level (where supported) and as post-processing."""

    year_from: int | None = None
    year_to: int | None = None
    years: list[int] | None = None  # explicit list; mutually exclusive with from/to range
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    # Field-scoping: "title" | "abstract" | "all" (default)
    field: str = "all"
    # Raw query override: sent directly to the source API, bypassing field transformation
    raw_query: str = ""

    def match(self, paper: Paper) -> bool:
        """Return True if paper passes all active filters."""
        if paper.year is not None:
            if self.years is not None:
                if paper.year not in self.years:
                    return False
            else:
                if self.year_from is not None and paper.year < self.year_from:
                    return False
                if self.year_to is not None and paper.year > self.year_to:
                    return False
        if self.authors:
            names = [a for a in paper.authors if a]
            if not any(_author_matches(f, names) for f in self.authors):
                return False
        return not (
            self.journal
            and (not paper.journal or self.journal.lower() not in paper.journal.lower())
        )

    @staticmethod
    def parse_year(value: str) -> SearchFilters:
        """
        Parse a year string into a SearchFilters instance.
          "2020"           → exact year
          "2020-2024"      → inclusive range
          "2020,2022,2024" → explicit list
        """
        f = SearchFilters()
        value = value.strip()
        if "," in value:
            f.years = [int(y.strip()) for y in value.split(",")]
        elif "-" in value:
            parts = value.split("-")
            f.year_from, f.year_to = int(parts[0]), int(parts[1])
        else:
            yr = int(value)
            f.year_from = f.year_to = yr
        return f


@dataclass
class Paper:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pii: str | None = None
    abstract: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    pdf_url: str | None = None
    source: str = ""
    is_open_access: bool = False
    url: str | None = None
    citation_count: int | None = None
    relevance_score: float | None = None
    openalex_id: str | None = None

    def to_dict(self) -> dict:
        """Serialise to a plain dict (thread-safe passing, JSON export)."""
        from dataclasses import asdict

        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Paper:
        """Reconstruct a Paper from a dict produced by ``to_dict``."""
        return cls(**d)

    @property
    def uid(self) -> str:
        """Best available unique identifier."""
        if self.doi:
            doi_lower = self.doi.lower()
            # Normalize arXiv DOIs (10.48550/arxiv.XXXX) to arxiv: prefix so
            # the same paper from arXiv + OpenAlex/EPMC deduplicates correctly.
            if doi_lower.startswith("10.48550/arxiv."):
                return f"arxiv:{doi_lower.removeprefix('10.48550/arxiv.')}"
            return f"doi:{doi_lower}"
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        if self.pii:
            return f"pii:{self.pii}"
        return f"title:{self.title.lower()[:80]}"

    @property
    def short_authors(self) -> str:
        if not self.authors:
            return "Unknown"
        if len(self.authors) == 1:
            return self.authors[0]
        if len(self.authors) == 2:
            return f"{self.authors[0]} & {self.authors[1]}"
        return f"{self.authors[0]} et al."

    def safe_filename(self, pattern: str = "{year}_{source}_{author}_{title}") -> str:
        def _slug(text: str, max_len: int = 60) -> str:
            s = re.sub(r"[^\w\s-]", "", text)[:max_len].strip()
            return re.sub(r"\s+", "_", s)

        year = str(self.year) if self.year else "0000"
        source = _slug(self.source)
        # First word of the first non-blank author (blank names must not crash)
        first_author = next((a.strip() for a in self.authors if a and a.strip()), "")
        author = _slug(first_author.split()[0]) if first_author else "Unknown"
        title = _slug(self.title)
        doi = re.sub(r"[^\w.-]", "_", self.doi) if self.doi else "no_doi"
        journal = _slug(self.journal) if self.journal else "no_journal"

        name = pattern.format(
            year=year, source=source, author=author, title=title, doi=doi, journal=journal
        )
        # strip any remaining filesystem-unsafe chars and collapse separators
        name = re.sub(r"[^\w\s.\-_]", "", name).strip("_")
        return name + ".pdf"
