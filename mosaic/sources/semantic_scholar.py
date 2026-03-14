"""Semantic Scholar Academic Graph API."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import parse_authors_name_key
from mosaic.sources.base import BaseSource

_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,authors,year,abstract,externalIds,openAccessPdf,publicationVenue,journal,isOpenAccess,citationCount"


class SemanticScholarSource(BaseSource):
    name = "Semantic Scholar"

    def __init__(self, api_key: str = ""):
        self._headers = {"x-api-key": api_key} if api_key else {}

    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Search the Semantic Scholar paper search endpoint.

        Translates the query and optional year filters into Semantic Scholar
        API parameters. Supports optional API key for higher rate limits.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters; ``raw_query`` overrides ``query``.
                Year constraints are forwarded as Semantic Scholar's
                ``year`` parameter (e.g. ``"2020-2023"``).

        Returns:
            A list of Paper objects from the ``data`` array in the response.
        """
        q = filters.raw_query if filters and filters.raw_query else query
        params: dict = {"query": q, "limit": min(max_results, 100), "fields": _FIELDS}
        if filters:
            # SS supports year=YYYY or year=YYYY-YYYY
            if filters.years:
                params["year"] = f"{min(filters.years)}-{max(filters.years)}"
            elif filters.year_from or filters.year_to:
                y_from = filters.year_from or filters.year_to
                y_to = filters.year_to or filters.year_from
                params["year"] = f"{y_from}-{y_to}" if y_from != y_to else str(y_from)
        with httpx.Client(timeout=30, headers=self._headers) as client:
            resp = client.get(
                f"{_BASE}/paper/search",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        return [self._parse(item) for item in data.get("data", [])]

    def _parse(self, item: dict) -> Paper:
        """Parse a single Semantic Scholar result dict into a Paper.

        Args:
            item: A dict representing one paper from the Semantic Scholar
                ``data`` array, containing fields such as ``title``,
                ``authors``, ``year``, ``externalIds``, ``openAccessPdf``,
                ``publicationVenue``, ``journal``, and ``isOpenAccess``.

        Returns:
            A Paper populated with available bibliographic metadata.
        """
        ext = item.get("externalIds") or {}
        oa_pdf = item.get("openAccessPdf") or {}
        venue = item.get("publicationVenue") or {}
        journal = item.get("journal") or {}

        authors = parse_authors_name_key(item.get("authors") or [])

        return Paper(
            title=item.get("title") or "",
            authors=authors,
            year=item.get("year"),
            doi=ext.get("DOI"),
            arxiv_id=ext.get("ArXiv"),
            abstract=item.get("abstract"),
            journal=journal.get("name") or venue.get("name"),
            pdf_url=oa_pdf.get("url"),
            source=self.name,
            is_open_access=item.get("isOpenAccess", False),
            url=f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
            citation_count=item.get("citationCount"),
        )
