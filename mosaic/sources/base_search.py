"""BASE (Bielefeld Academic Search Engine) API source."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import extract_first, parse_year
from mosaic.sources.base import BaseSource, build_field_query

_BASE = "https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi"


class BASESource(BaseSource):
    name = "BASE"

    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Search the BASE (Bielefeld Academic Search Engine) API.

        Translates the query into BASE Lucene syntax, scoping to
        ``dctitle`` or ``dcabstract`` when a field filter is set. Author,
        journal, and year constraints are appended as Lucene clauses.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping, authors, journal, and
                year range or specific years. ``raw_query`` overrides the
                default mapping if set.

        Returns:
            A list of Paper objects parsed from the ``response.docs`` array.
        """
        base_query = build_field_query(query, filters, 'dctitle:"{}"', 'dcabstract:"{}"')
        if filters:
            if filters.authors:
                for author in filters.authors:
                    base_query += f' AND dccreator:"{author}"'
            if filters.journal:
                base_query += f' AND dcsource:"{filters.journal}"'
            if filters.years:
                years_expr = " OR ".join(f"dcyear:{y}" for y in filters.years)
                base_query += f" AND ({years_expr})"
            elif filters.year_from or filters.year_to:
                y_from = filters.year_from or filters.year_to
                y_to = filters.year_to or filters.year_from
                base_query += f" AND dcyear:[{y_from} TO {y_to}]"

        with httpx.Client(timeout=30) as client:
            resp = client.get(
                _BASE,
                params={
                    "func": "PerformSearch",
                    "query": base_query,
                    "hits": min(max_results, 100),
                    "offset": 0,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            docs = resp.json().get("response", {}).get("docs", [])
        return [self._parse(doc) for doc in docs]

    def _parse(self, doc: dict) -> Paper:
        """Parse a single BASE result document dict into a Paper.

        Args:
            doc: A dict from the BASE ``response.docs`` array, containing
                Dublin Core fields such as ``dctitle``, ``dccreator``,
                ``dcyear``, ``dcdoi``, ``dcdescription``, ``dcsource``,
                ``dclink``, ``dcoa``, and ``dcformat``.

        Returns:
            A Paper with a PDF URL set when the article is open access and
            its format indicates a PDF.
        """
        title = extract_first(doc.get("dctitle")) or ""
        authors = doc.get("dccreator") or []
        if isinstance(authors, str):
            authors = [authors]

        year = parse_year(doc.get("dcyear"))

        doi = doc.get("dcdoi") or None
        abstract = extract_first(doc.get("dcdescription"))
        journal = extract_first(doc.get("dcsource"))
        url = doc.get("dclink")

        is_oa = doc.get("dcoa") == 1
        fmt = extract_first(doc.get("dcformat")) or ""
        pdf_url = url if (is_oa and "pdf" in fmt.lower()) else None

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            abstract=abstract,
            journal=journal,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=is_oa,
            url=url,
        )
