"""DOAJ (Directory of Open Access Journals) API."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://doaj.org/api/v3/search/articles"


class DoajSource(BaseSource):
    name = "DOAJ"

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        """Search the DOAJ v3 article search endpoint.

        Translates the query into DOAJ Lucene syntax, scoping to
        ``bibjson.title`` or ``bibjson.abstract`` when a field filter is set.
        Author, journal, and year constraints are appended as Lucene clauses.

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
            doaj_query = filters.raw_query
        elif filters and filters.field == "title":
            doaj_query = f'bibjson.title:"{query}"'
        elif filters and filters.field == "abstract":
            doaj_query = f'bibjson.abstract:"{query}"'
        else:
            doaj_query = query
        if filters:
            if filters.authors:
                for author in filters.authors:
                    doaj_query += f' AND bibjson.author.name:"{author}"'
            if filters.journal:
                doaj_query += f' AND bibjson.journal.title:"{filters.journal}"'
            if filters.years:
                years_expr = " OR ".join(f"bibjson.year:{y}" for y in filters.years)
                doaj_query += f" AND ({years_expr})"
            else:
                if filters.year_from:
                    doaj_query += f" AND bibjson.year:>={filters.year_from}"
                if filters.year_to:
                    doaj_query += f" AND bibjson.year:<={filters.year_to}"
        # DOAJ uses path-based query: /search/articles/{query}
        resp = httpx.get(
            f"https://doaj.org/api/v3/search/articles/{httpx.URL(doaj_query)}",
            params={"pageSize": min(max_results, 100)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return [self._parse(item) for item in data.get("results", [])]

    def _parse(self, item: dict) -> Paper:
        """Parse a single DOAJ result dict into a Paper.

        Args:
            item: A dict from the DOAJ ``results`` array containing a
                ``bibjson`` sub-object with title, authors, identifiers,
                journal, and link information.

        Returns:
            A Paper marked as open access (DOAJ only indexes OA articles).
        """
        bib = item.get("bibjson") or {}
        journal = bib.get("journal") or {}
        identifiers = {i["type"]: i["id"] for i in bib.get("identifier", []) if "type" in i and "id" in i}

        authors = [a.get("name", "") for a in bib.get("author", [])]

        year_str = bib.get("year") or ""
        year = int(year_str) if year_str.isdigit() else None

        pdf_url = None
        for link in bib.get("link", []):
            if link.get("type") == "fulltext" or link.get("content_type") == "PDF":
                pdf_url = link.get("url")
                break

        return Paper(
            title=bib.get("title") or "",
            authors=authors,
            year=year,
            doi=identifiers.get("doi"),
            abstract=bib.get("abstract"),
            journal=journal.get("title"),
            volume=journal.get("volume"),
            issue=journal.get("number"),
            pages=bib.get("start_page"),
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=True,
            url=f"https://doaj.org/article/{item.get('id', '')}",
        )
