"""BASE (Bielefeld Academic Search Engine) API source."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi"


class BASESource(BaseSource):
    name = "BASE"

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        if filters and filters.raw_query:
            base_query = filters.raw_query
        elif filters and filters.field == "title":
            base_query = f'dctitle:"{query}"'
        elif filters and filters.field == "abstract":
            base_query = f'dcabstract:"{query}"'
        else:
            base_query = query
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
                y_to   = filters.year_to   or filters.year_from
                base_query += f" AND dcyear:[{y_from} TO {y_to}]"

        resp = httpx.get(_BASE, params={
            "func": "PerformSearch",
            "query": base_query,
            "hits": min(max_results, 100),
            "offset": 0,
            "format": "json",
        }, timeout=30)
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        return [self._parse(doc) for doc in docs]

    def _parse(self, doc: dict) -> Paper:
        title = _first(doc.get("dctitle")) or ""
        authors = doc.get("dccreator") or []
        if isinstance(authors, str):
            authors = [authors]

        year_str = str(doc.get("dcyear") or "")
        year = int(year_str) if year_str.isdigit() else None

        doi = doc.get("dcdoi") or None
        abstract = _first(doc.get("dcdescription"))
        journal = _first(doc.get("dcsource"))
        url = doc.get("dclink")

        is_oa = doc.get("dcoa") == 1
        fmt = _first(doc.get("dcformat")) or ""
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


def _first(value: str | list | None) -> str | None:
    """Return the first element if a list, the value itself if a string, else None."""
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value
