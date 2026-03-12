"""Scopus API source (Elsevier Scopus Search API).

Uses the official Elsevier Scopus Search API, which requires a free API key
registered at https://dev.elsevier.com. Full metadata (abstracts, complete
author lists) requires an institutional subscription; partial metadata
(title, first author, journal, year, DOI, citation count, open-access flag)
is available with a free key alone.
"""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.elsevier.com/content/search/scopus"

# Fields to request; ABSTRACT and full author list require institutional access
_FIELDS = (
    "dc:identifier,eid,dc:title,dc:creator,author,dc:description,"
    "prism:publicationName,prism:volume,prism:issueIdentifier,"
    "prism:pageRange,prism:coverDate,prism:doi,citedby-count,"
    "openaccess,link"
)


class ScopusAPISource(BaseSource):
    """Search source for Scopus via the Elsevier Scopus Search API.

    Covers 90+ million records from peer-reviewed journals, conference
    proceedings, and book series across all disciplines. Requires a free API
    key; an optional institutional token enables full abstracts and complete
    author lists for subscribers.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "Scopus"

    def __init__(self, api_key: str = "", inst_token: str = "") -> None:
        """Initialise the Scopus API source.

        Args:
            api_key: Elsevier API key from https://dev.elsevier.com.
                The source is disabled when this is empty.
            inst_token: Optional institutional token for full metadata access.
                Enables abstracts and complete author lists for subscribers.
        """
        self._api_key = api_key
        self._inst_token = inst_token

    def available(self) -> bool:
        """Return True only when a Scopus API key has been configured.

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
        """Search the Scopus Search API.

        Translates the query into Scopus boolean query syntax. Title and
        abstract field scoping use the native ``TITLE()`` and ``ABS()``
        operators; the default searches ``TITLE-ABS-KEY()``. Year, author,
        and journal filters are appended natively using Scopus field codes.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 200).
            filters: Optional filters for field scoping, year range, authors,
                and journal. ``raw_query`` overrides the default mapping.

        Returns:
            A list of Paper objects parsed from the ``search-results.entry``
            array. Entries without a title are silently skipped.
        """
        if filters and filters.raw_query:
            scopus_query = filters.raw_query
        elif filters and filters.field == "title":
            scopus_query = f'TITLE("{query}")'
        elif filters and filters.field == "abstract":
            scopus_query = f'ABS("{query}")'
        else:
            scopus_query = f'TITLE-ABS-KEY("{query}")'

        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from:
                scopus_query += f" AND PUBYEAR > {y_from - 1}"
            if y_to:
                scopus_query += f" AND PUBYEAR < {y_to + 1}"
            if filters.authors:
                for author in filters.authors:
                    scopus_query += f' AND AUTH("{author}")'
            if filters.journal:
                scopus_query += f' AND SRCTITLE("{filters.journal}")'

        headers: dict[str, str] = {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/json",
        }
        if self._inst_token:
            headers["X-ELS-Insttoken"] = self._inst_token

        resp = httpx.get(
            _BASE,
            params={"query": scopus_query, "count": min(max_results, 200), "field": _FIELDS},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        entries = resp.json().get("search-results", {}).get("entry", []) or []
        return [
            self._parse(e) for e in entries
            if isinstance(e, dict) and "dc:title" in e
        ]

    def _parse(self, item: dict) -> Paper:
        """Parse a single Scopus search entry dict into a Paper.

        Args:
            item: A dict from the Scopus ``search-results.entry`` array.
                Key fields: ``dc:title``, ``dc:creator`` (first author string,
                always present with free-tier key), ``author`` (list of dicts
                with ``authname``, institutional access only),
                ``prism:coverDate`` (YYYY-MM-DD), ``prism:doi``,
                ``prism:publicationName``, ``citedby-count``,
                ``openaccess`` ("0" or "1"), ``link`` (list of dicts with
                ``@ref`` and ``@href``).

        Returns:
            A Paper with ``citation_count`` populated when available.
            ``pdf_url`` is always ``None`` — Scopus does not provide direct
            PDF links via the Search API.
        """
        title = item.get("dc:title") or ""

        # Full author list requires institutional access; fall back to
        # dc:creator (first author string, always present with free key).
        authors: list[str] = []
        author_list = item.get("author") or []
        if isinstance(author_list, list):
            authors = [a.get("authname", "") for a in author_list if a.get("authname")]
        if not authors:
            creator = item.get("dc:creator") or ""
            if creator:
                authors = [creator]

        year: int | None = None
        cover_date = item.get("prism:coverDate") or ""
        if len(cover_date) >= 4:
            try:
                year = int(cover_date[:4])
            except ValueError:
                pass

        doi = item.get("prism:doi") or None
        abstract = item.get("dc:description") or None
        journal = item.get("prism:publicationName") or None
        volume = item.get("prism:volume") or None
        issue = item.get("prism:issueIdentifier") or None
        pages = item.get("prism:pageRange") or None

        citation_count: int | None = None
        raw_count = item.get("citedby-count")
        if raw_count is not None:
            try:
                citation_count = int(raw_count)
            except (ValueError, TypeError):
                pass

        oa_raw = item.get("openaccess")
        is_oa = oa_raw in ("1", 1, True)

        url: str | None = None
        for link in (item.get("link") or []):
            if isinstance(link, dict) and link.get("@ref") == "scopus":
                url = link.get("@href") or None
                break

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            abstract=abstract,
            journal=journal,
            volume=volume,
            issue=issue,
            pages=pages,
            url=url,
            pdf_url=None,
            source=self.name,
            is_open_access=is_oa,
            citation_count=citation_count,
        )
