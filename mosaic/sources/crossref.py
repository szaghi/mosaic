"""Crossref REST API search source."""
from __future__ import annotations
import re
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://api.crossref.org/works"


class CrossrefSource(BaseSource):
    """Search source for Crossref, the DOI registration agency.

    Crossref indexes 150 million+ scholarly works deposited by publishers,
    including journal articles, conference papers, books, and datasets. No
    authentication is required; providing an email in the ``mailto`` parameter
    opts into the polite pool with higher rate limits (50 req/s).

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "Crossref"

    def __init__(self, email: str = "") -> None:
        """Initialise the Crossref source.

        Args:
            email: Optional email address passed as the ``mailto`` query
                parameter. This opts the client into Crossref's polite pool,
                which grants up to 50 requests per second and better service
                quality. The Unpaywall email from config is reused here — no
                separate key is needed.
        """
        self._email = email

    def available(self) -> bool:
        """Return True — Crossref requires no credentials.

        Returns:
            Always True.
        """
        return True

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        """Search the Crossref works endpoint.

        Supports scoping to title via ``query.title`` or to bibliographic
        fields via ``query.bibliographic``. Year, author, and journal
        constraints are applied as post-processing only (the framework handles
        this automatically via ``SearchFilters``).

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping and post-processing.
                ``raw_query`` overrides the default mapping if set.

        Returns:
            A list of Paper objects parsed from the ``message.items`` array.
        """
        if filters and filters.raw_query:
            params: dict = {"query": filters.raw_query}
        elif filters and filters.field == "title":
            params = {"query.title": query}
        elif filters and filters.field == "abstract":
            params = {"query.bibliographic": query}
        else:
            params = {"query": query}

        params["rows"] = min(max_results, 100)
        if self._email:
            params["mailto"] = self._email

        resp = httpx.get(_BASE, params=params, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
        return [self._parse(item) for item in items]

    def _parse(self, item: dict) -> Paper:
        """Parse a single Crossref works item dict into a Paper.

        Args:
            item: A dict from the Crossref ``message.items`` array, containing
                ``title``, ``author``, ``published``, ``DOI``, ``abstract``,
                ``container-title``, ``link``, and ``URL`` fields.

        Returns:
            A Paper with ``is_open_access`` set to True when a PDF link is
            found in the ``link`` array.
        """
        # title is a list; take the first element
        title_list = item.get("title") or []
        title = title_list[0] if title_list else ""

        # authors: list of {given, family} dicts → "Family, Given"
        raw_authors = item.get("author") or []
        authors: list[str] = []
        for a in raw_authors:
            family = a.get("family", "")
            given = a.get("given", "")
            if family and given:
                authors.append(f"{family}, {given}")
            elif family:
                authors.append(family)
            elif given:
                authors.append(given)

        # year: published.date-parts[0][0]
        year: int | None = None
        date_parts = item.get("published", {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            try:
                year = int(date_parts[0][0])
            except (TypeError, ValueError):
                year = None

        doi = item.get("DOI") or None

        # abstract may contain JATS XML tags — strip them
        raw_abstract = item.get("abstract") or ""
        abstract = re.sub(r"<[^>]+>", " ", raw_abstract).strip() or None

        # journal: container-title is a list; take the first element
        container = item.get("container-title") or []
        journal = container[0] if container else None

        # URL: canonical DOI URL
        url = item.get("URL") or None

        # PDF URL: find link entry with content-type == "application/pdf"
        pdf_url: str | None = None
        for link in (item.get("link") or []):
            if link.get("content-type") == "application/pdf":
                pdf_url = link.get("URL") or None
                break

        is_open_access = pdf_url is not None

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
            is_open_access=is_open_access,
        )
