"""OpenAlex API source (https://openalex.org)."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.openalex.org/works"
_SELECT = (
    "id,title,authorships,publication_year,doi,ids,"
    "abstract_inverted_index,primary_location,best_oa_location,"
    "open_access,biblio"
)


class OpenAlexSource(BaseSource):
    name = "OpenAlex"

    def __init__(self, email: str = ""):
        self._email = email

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        params: dict = {
            "search": query,
            "per_page": min(max_results, 200),
            "select": _SELECT,
        }
        if self._email:
            params["mailto"] = self._email

        filter_parts: list[str] = []
        if filters:
            if filters.years:
                filter_parts.append(f"publication_year:{min(filters.years)}-{max(filters.years)}")
            elif filters.year_from or filters.year_to:
                y_from = filters.year_from or filters.year_to
                y_to   = filters.year_to   or filters.year_from
                filter_parts.append(f"publication_year:{y_from}-{y_to}")
        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        resp = httpx.get(_BASE, params=params, timeout=30)
        resp.raise_for_status()
        return [self._parse(item) for item in resp.json().get("results", [])]

    def _parse(self, item: dict) -> Paper:
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in item.get("authorships", [])
        ]

        doi_raw = item.get("doi") or ""
        doi = doi_raw.removeprefix("https://doi.org/") or None

        ids = item.get("ids") or {}
        arxiv_raw = ids.get("arxiv") or ""
        arxiv_id = arxiv_raw.removeprefix("https://arxiv.org/abs/") or None

        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

        primary = item.get("primary_location") or {}
        source  = primary.get("source") or {}
        journal = source.get("display_name")

        biblio  = item.get("biblio") or {}
        oa      = item.get("open_access") or {}
        best_oa = item.get("best_oa_location") or {}

        pdf_url = best_oa.get("pdf_url") or primary.get("pdf_url")

        return Paper(
            title=item.get("title") or "",
            authors=authors,
            year=item.get("publication_year"),
            doi=doi,
            arxiv_id=arxiv_id,
            abstract=abstract,
            journal=journal,
            volume=biblio.get("volume"),
            issue=biblio.get("issue"),
            pages=_pages(biblio),
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=oa.get("is_oa", False),
            url=item.get("id"),
        )


def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Reconstruct plain text from OpenAlex inverted-index abstract format."""
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, pos_list in inverted_index.items():
        for pos in pos_list:
            positions.append((pos, word))
    positions.sort()
    return " ".join(word for _, word in positions)


def _pages(biblio: dict) -> str | None:
    first = biblio.get("first_page")
    last  = biblio.get("last_page")
    if first and last:
        return f"{first}-{last}"
    return first or last or None
