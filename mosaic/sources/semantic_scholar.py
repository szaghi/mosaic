"""Semantic Scholar Academic Graph API."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,authors,year,abstract,externalIds,openAccessPdf,publicationVenue,journal,isOpenAccess"


class SemanticScholarSource(BaseSource):
    name = "Semantic Scholar"

    def __init__(self, api_key: str = ""):
        self._headers = {"x-api-key": api_key} if api_key else {}

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        q = (filters.raw_query if filters and filters.raw_query else query)
        params: dict = {"query": q, "limit": min(max_results, 100), "fields": _FIELDS}
        if filters:
            # SS supports year=YYYY or year=YYYY-YYYY
            if filters.years:
                params["year"] = f"{min(filters.years)}-{max(filters.years)}"
            elif filters.year_from or filters.year_to:
                y_from = filters.year_from or filters.year_to
                y_to   = filters.year_to   or filters.year_from
                params["year"] = f"{y_from}-{y_to}" if y_from != y_to else str(y_from)
        resp = httpx.get(
            f"{_BASE}/paper/search",
            params=params,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return [self._parse(item) for item in data.get("data", [])]

    def _parse(self, item: dict) -> Paper:
        ext = item.get("externalIds") or {}
        oa_pdf = item.get("openAccessPdf") or {}
        venue = item.get("publicationVenue") or {}
        journal = item.get("journal") or {}

        authors = [a.get("name", "") for a in item.get("authors", [])]

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
        )
