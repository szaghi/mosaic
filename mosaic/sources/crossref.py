"""Crossref REST API search source."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import (
    extract_first,
    normalise_doi,
    parse_authors_given_family,
    parse_year,
    strip_html,
)
from mosaic.sources.base import BaseSource, extract_year_range, with_retry

_BASE = "https://api.crossref.org/works"

# ``link.intended-application`` values that mark subscriber-only TDM copies.
_TDM_APPLICATIONS = frozenset({"text-mining", "similarity-checking"})


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

        Supports scoping to title via ``query.title``. Crossref has no
        abstract-only query field (``query.bibliographic`` covers titles,
        authors and venues, not abstracts), so abstract scoping falls back to
        the general ``query``. Year ranges are sent as native
        ``from-pub-date``/``until-pub-date`` filters, and author / journal
        filters as ``query.author`` / ``query.container-title`` relevance
        hints; the framework still post-filters on all of them.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping and native filtering.
                ``raw_query`` overrides the default mapping if set.

        Returns:
            A list of Paper objects parsed from the ``message.items`` array.
        """
        if filters and filters.raw_query:
            params: dict = {"query": filters.raw_query}
        elif filters and filters.field == "title":
            params = {"query.title": query}
        else:
            params = {"query": query}

        if filters:
            y_from, y_to = extract_year_range(filters)
            date_filters = []
            if y_from:
                date_filters.append(f"from-pub-date:{y_from}-01-01")
            if y_to:
                date_filters.append(f"until-pub-date:{y_to}-12-31")
            if date_filters:
                params["filter"] = ",".join(date_filters)
            if filters.authors:
                params["query.author"] = " ".join(filters.authors)
            if filters.journal:
                params["query.container-title"] = filters.journal

        params["rows"] = min(max_results, 100)
        if self._email:
            params["mailto"] = self._email

        with httpx.Client(timeout=30) as client:
            resp = with_retry(lambda: client.get(_BASE, params=params))
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
            A Paper with ``is_open_access`` set to True only when the work
            carries a Creative Commons license. ``pdf_url`` comes from the
            ``link`` array, ignoring text-mining / similarity-checking links
            (those point at paywalled full text for TDM subscribers).
        """
        # title is a list; take the first element
        # Crossref titles carry inline markup (<i>, <sub>) and HTML entities
        title = strip_html(extract_first(item.get("title")), sep="") or ""

        # authors: list of {given, family} dicts → "Family, Given"
        authors = parse_authors_given_family(item.get("author") or [])

        # year: published.date-parts[0][0]
        year: int | None = None
        date_parts = item.get("published", {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            year = parse_year(date_parts[0][0])

        doi = normalise_doi(item.get("DOI"))

        # abstract may contain JATS XML tags — strip them
        abstract = strip_html(item.get("abstract"))

        # journal: container-title is a list; take the first element
        journal = strip_html(extract_first(item.get("container-title")), sep="")

        # URL: canonical DOI URL
        url = item.get("URL") or None

        # Open access: a Creative Commons license is the only reliable signal.
        is_open_access = any(
            "creativecommons.org" in str(lic.get("URL") or "").lower()
            for lic in item.get("license") or []
            if isinstance(lic, dict)
        )

        # PDF URL: first application/pdf link not reserved for text mining.
        pdf_url: str | None = None
        for link in item.get("link") or []:
            if link.get("content-type") != "application/pdf":
                continue
            if link.get("intended-application") in _TDM_APPLICATIONS:
                continue
            pdf_url = link.get("URL") or None
            if pdf_url:
                break

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
