"""CORE (core.ac.uk) open-access aggregator API."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.core.ac.uk/v3/search/works"


class CORESource(BaseSource):
    name = "CORE"

    def __init__(self, api_key: str = ""):
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def available(self) -> bool:
        return bool(self._headers)

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        core_query = query
        if filters:
            if filters.authors:
                for author in filters.authors:
                    core_query += f' AND authors.name:"{author}"'
            if filters.journal:
                core_query += f' AND journals.title:"{filters.journal}"'
            if filters.years:
                y_min, y_max = min(filters.years), max(filters.years)
                core_query += f" AND yearPublished>={y_min} AND yearPublished<={y_max}"
            elif filters.year_from or filters.year_to:
                y_from = filters.year_from or filters.year_to
                y_to   = filters.year_to   or filters.year_from
                core_query += f" AND yearPublished>={y_from} AND yearPublished<={y_to}"

        resp = httpx.get(_BASE, params={
            "q": core_query,
            "limit": min(max_results, 100),
            "offset": 0,
        }, headers=self._headers, timeout=30)
        resp.raise_for_status()
        return [self._parse(item) for item in resp.json().get("results", [])]

    def _parse(self, item: dict) -> Paper:
        authors = [a.get("name", "") for a in (item.get("authors") or [])]

        journals = item.get("journals") or []
        journal = journals[0].get("title") if journals else None

        core_id = item.get("id")

        return Paper(
            title=item.get("title") or "",
            authors=authors,
            year=item.get("yearPublished"),
            doi=item.get("doi") or None,
            abstract=item.get("abstract"),
            journal=journal,
            pdf_url=item.get("downloadUrl") or None,
            source=self.name,
            is_open_access=item.get("isOpenAccess", False),
            url=f"https://core.ac.uk/works/{core_id}" if core_id else None,
        )
