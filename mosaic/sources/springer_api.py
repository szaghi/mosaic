"""Springer Nature Open Access API source.

Uses the official Springer Nature Open Access JSON endpoint, which requires
a free API key and returns only openly accessible articles. This source
complements the browser-based Springer source (``sp``) — the API source
is faster and includes direct PDF links; the browser source requires no
credentials and covers all Springer content, not just OA.
"""
from __future__ import annotations
import re
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.springernature.com/openaccess/json"


class SpringerAPISource(BaseSource):
    """Search source for the Springer Nature Open Access API.

    Returns only open-access articles from Springer, Nature, and affiliated
    journals. Requires a free API key registered at dev.springernature.com.
    Includes direct PDF links when present in the ``url`` array of each record.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "Springer Nature"

    def __init__(self, api_key: str = "") -> None:
        """Initialise the Springer Nature API source.

        Args:
            api_key: A Springer Nature API key obtained free of charge at
                https://dev.springernature.com. The source is disabled when
                this is empty.
        """
        self._api_key = api_key

    def available(self) -> bool:
        """Return True only when a Springer Nature API key has been configured.

        Returns:
            True if an API key is set, False otherwise.
        """
        return bool(self._api_key)

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        """Search the Springer Nature Open Access JSON endpoint.

        Translates the query into Springer query syntax, scoping to
        ``title:`` when requested. Year constraints are appended as
        ``date:YYYY-YYYY`` clauses. Author and journal filters are applied
        as post-processing by the framework.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping and year range.
                ``raw_query`` overrides the default mapping if set. Author
                and journal filters are applied as post-processing.

        Returns:
            A list of Paper objects parsed from the ``records`` array.
        """
        if filters and filters.raw_query:
            q = filters.raw_query
        elif filters and filters.field == "title":
            q = f'title:"{query}"'
        else:
            q = query

        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                q += f" date:{y_from or y_to}-{y_to or y_from}"

        resp = httpx.get(
            _BASE,
            params={
                "q": q,
                "p": min(max_results, 100),
                "api_key": self._api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return [self._parse(r) for r in resp.json().get("records", [])]

    def _parse(self, record: dict) -> Paper:
        """Parse a single Springer Open Access record into a Paper.

        Args:
            record: A dict from the Springer ``records`` array, containing
                fields such as ``title`` (str), ``creators`` (list of
                ``{creator: "Last, First"}``), ``publicationDate`` (str),
                ``doi`` (str), ``abstract`` (str), ``publicationName`` (str),
                ``openaccess`` (str), and ``url`` (list of
                ``{format, platform, value}`` dicts).

        Returns:
            A Paper with ``is_open_access=True`` (the endpoint guarantees OA)
            and a PDF URL extracted from the ``url`` array when present.
        """
        title = record.get("title") or ""

        creators = record.get("creators") or []
        authors = [c.get("creator", "") for c in creators if c.get("creator")]

        pub_date = record.get("publicationDate") or ""
        year: int | None = None
        m = re.match(r"(\d{4})", pub_date)
        if m:
            year = int(m.group(1))

        doi = record.get("doi") or None

        abstract = record.get("abstract") or None

        journal = record.get("publicationName") or None

        # url array: pick html for landing page, pdf for download
        url: str | None = None
        pdf_url: str | None = None
        for entry in (record.get("url") or []):
            fmt = entry.get("format", "")
            val = entry.get("value", "")
            if fmt == "html" and not url:
                url = val or None
            elif fmt == "pdf" and not pdf_url:
                pdf_url = val or None

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            abstract=abstract,
            journal=journal,
            url=url,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=True,
        )
