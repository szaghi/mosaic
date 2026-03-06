"""Unified paper data model."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SearchFilters:
    """Filters applied both at the API level (where supported) and as post-processing."""
    year_from: int | None = None
    year_to: int | None = None
    years: list[int] | None = None   # explicit list; mutually exclusive with from/to range
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    # Field-scoping: "title" | "abstract" | "all" (default)
    field: str = "all"
    # Raw query override: sent directly to the source API, bypassing field transformation
    raw_query: str = ""

    def match(self, paper: "Paper") -> bool:
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
            combined = " ".join(paper.authors).lower()
            if not any(a.lower() in combined for a in self.authors):
                return False
        if self.journal:
            if not paper.journal or self.journal.lower() not in paper.journal.lower():
                return False
        return True

    @staticmethod
    def parse_year(value: str) -> "SearchFilters":
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

    @property
    def uid(self) -> str:
        """Best available unique identifier."""
        if self.doi:
            return f"doi:{self.doi.lower()}"
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

    def safe_filename(self) -> str:
        import re
        parts = [self.short_authors.split()[0] if self.authors else "Unknown"]
        if self.year:
            parts.append(str(self.year))
        slug = re.sub(r"[^\w\s-]", "", self.title)[:60].strip()
        slug = re.sub(r"\s+", "_", slug)
        parts.append(slug)
        return "_".join(parts) + ".pdf"
