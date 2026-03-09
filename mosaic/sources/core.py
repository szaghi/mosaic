"""CORE (core.ac.uk) open-access aggregator API."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.core.ac.uk/v3/search/works/"


class CORESource(BaseSource):
    name = "CORE"

    def __init__(self, api_key: str = ""):
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def available(self) -> bool:
        """Return True only when a CORE API key has been configured."""
        return bool(self._headers)

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        """Search the CORE v3 works search endpoint.

        Translates the query into CORE query syntax, scoping to ``title`` or
        ``abstract`` fields when requested. Author, journal, and year
        constraints are appended as CORE field clauses.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping, authors, journal, and
                year range or specific years. ``raw_query`` overrides the
                default mapping if set.

        Returns:
            A list of Paper objects parsed from the ``results`` array.
        """
        if filters and filters.raw_query:
            core_query = filters.raw_query
        elif filters and filters.field == "title":
            core_query = f'title:"{query}"'
        elif filters and filters.field == "abstract":
            core_query = f'abstract:"{query}"'
        else:
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
        """Parse a single CORE result dict into a Paper.

        Args:
            item: A dict from the CORE ``results`` array, containing fields
                such as ``title``, ``authors``, ``yearPublished``, ``doi``,
                ``abstract``, ``journals``, ``downloadUrl``,
                ``isOpenAccess``, and ``id``.

        Returns:
            A Paper with a URL pointing to the CORE works page when an ID
            is present.
        """
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
