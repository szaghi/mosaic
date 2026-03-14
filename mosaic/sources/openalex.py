"""OpenAlex API source (https://openalex.org)."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.openalex.org/works"
_SELECT = (
    "id,title,authorships,publication_year,doi,ids,"
    "abstract_inverted_index,primary_location,best_oa_location,"
    "open_access,biblio,cited_by_count"
)


class OpenAlexSource(BaseSource):
    name = "OpenAlex"

    def __init__(self, email: str = ""):
        self._email = email

    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Search the OpenAlex works endpoint.

        Uses the ``search`` parameter for full-text queries and the ``filter``
        parameter for field-scoped (title/abstract) or year-constrained
        queries. Optionally adds an email address via ``mailto`` for the
        polite pool.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 200).
            filters: Optional filters for field scoping, year range, and
                ``raw_query`` override. Year constraints are merged into the
                ``filter`` parameter alongside any field filters.

        Returns:
            A list of Paper objects parsed from the ``results`` array.
        """
        params: dict = {"per_page": min(max_results, 200), "select": _SELECT}
        if self._email:
            params["mailto"] = self._email

        if filters and filters.raw_query:
            params["search"] = filters.raw_query
        elif filters and filters.field == "title":
            params["filter"] = f"title.search:{query}"
        elif filters and filters.field == "abstract":
            params["filter"] = f"abstract.search:{query}"
        else:
            params["search"] = query

        filter_parts: list[str] = []
        if filters:
            if filters.years:
                filter_parts.append(f"publication_year:{min(filters.years)}-{max(filters.years)}")
            elif filters.year_from or filters.year_to:
                y_from = filters.year_from or filters.year_to
                y_to = filters.year_to or filters.year_from
                filter_parts.append(f"publication_year:{y_from}-{y_to}")
        if filter_parts:
            # Merge with any existing filter (e.g. title.search set above)
            existing = params.get("filter", "")
            params["filter"] = (
                ",".join([existing, *filter_parts]) if existing else ",".join(filter_parts)
            )

        with httpx.Client(timeout=30) as client:
            resp = client.get(_BASE, params=params)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        return [self._parse(item) for item in results]

    def _parse(self, item: dict) -> Paper:
        """Parse a single OpenAlex work dict into a Paper.

        Reconstructs the abstract from the inverted-index format, strips the
        ``https://doi.org/`` prefix from DOIs, and resolves the best available
        open-access PDF URL.

        Args:
            item: A dict from the OpenAlex ``results`` array, containing
                fields selected by ``_SELECT`` (title, authorships,
                publication_year, doi, ids, abstract_inverted_index,
                primary_location, best_oa_location, open_access, biblio).

        Returns:
            A Paper populated with available bibliographic metadata.
        """
        authors = [a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])]

        doi_raw = item.get("doi") or ""
        doi = doi_raw.removeprefix("https://doi.org/") or None

        ids = item.get("ids") or {}
        arxiv_raw = ids.get("arxiv") or ""
        arxiv_id = arxiv_raw.removeprefix("https://arxiv.org/abs/") or None

        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

        primary = item.get("primary_location") or {}
        source = primary.get("source") or {}
        journal = source.get("display_name")

        biblio = item.get("biblio") or {}
        oa = item.get("open_access") or {}
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
            citation_count=item.get("cited_by_count"),
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
    """Build a page-range string from an OpenAlex biblio dict.

    Args:
        biblio: The ``biblio`` sub-dict from an OpenAlex work, potentially
            containing ``first_page`` and ``last_page`` keys.

    Returns:
        A string like ``"123-130"``, a single page number string, or ``None``
        when neither key is present.
    """
    first = biblio.get("first_page")
    last = biblio.get("last_page")
    if first and last:
        return f"{first}-{last}"
    return first or last or None
