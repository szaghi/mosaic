"""DBLP Computer Science Bibliography search source."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource, build_field_query

_BASE = "https://dblp.org/search/publ/api"


class DBLPSource(BaseSource):
    """Search source for DBLP Computer Science Bibliography.

    DBLP indexes 6 million+ publications in computer science, covering journal
    articles, conference papers, and workshop proceedings. No authentication is
    required — the API is freely accessible without a key or email address.

    Note: DBLP does not provide abstracts. The ``abstract`` field is always
    ``None`` for DBLP results. The source is best suited for CS conference and
    journal papers where title, authors, venue, and year are sufficient.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "DBLP"

    def __init__(self) -> None:
        """Initialise the DBLP source.

        No credentials or configuration are required.
        """

    def available(self) -> bool:
        """Return True — DBLP requires no credentials.

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
        """Search the DBLP publication search API.

        DBLP does not support native year, author, or journal filters; all
        three are applied as post-processing by the framework. Field scoping
        to title uses the DBLP ``$`` suffix convention (``q={query}$``).

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 1000).
            filters: Optional filters for field scoping. ``raw_query``
                overrides the default mapping if set. Year, author, and journal
                filters are applied as post-processing only.

        Returns:
            A list of Paper objects parsed from the ``result.hits.hit`` array.
            Returns an empty list when no hits are present in the response.
        """
        q = build_field_query(query, filters, "{}$", "{}")

        params: dict = {
            "q": q,
            "h": min(max_results, 1000),
            "f": 0,
            "format": "json",
        }

        with httpx.Client(timeout=30) as client:
            resp = client.get(_BASE, params=params)
            resp.raise_for_status()
            hits = resp.json().get("result", {}).get("hits", {})
            raw_hits = hits.get("hit", [])
        if not raw_hits:
            return []
        return [self._parse(hit) for hit in raw_hits]

    def _parse(self, hit: dict) -> Paper:
        """Parse a single DBLP hit dict into a Paper.

        Args:
            hit: A dict from the DBLP ``result.hits.hit`` array. The ``info``
                sub-dict contains ``title``, ``authors`` (with an ``author``
                key that may be a single dict or a list of dicts), ``year``,
                ``doi``, ``url``, ``venue``, and ``ee`` fields.

        Returns:
            A Paper with ``abstract=None`` (DBLP provides no abstracts) and
            ``is_open_access`` set to True when the ``ee`` field points to an
            arXiv copy or a direct PDF.
        """
        info = hit.get("info", {})

        title = info.get("title") or ""

        # authors: info.authors.author may be a single dict or a list of dicts
        raw_author = info.get("authors", {}).get("author")
        if raw_author is None:
            authors: list[str] = []
        elif isinstance(raw_author, dict):
            authors = [raw_author.get("text", "")]
        else:
            authors = [a.get("text", "") for a in raw_author if a.get("text")]

        year: int | None = None
        try:
            year = int(info["year"])
        except (KeyError, TypeError, ValueError):
            year = None

        doi = info.get("doi") or None

        # venue → journal
        journal = info.get("venue") or None

        # url → DBLP record landing page
        url = info.get("url") or None

        # ee: electronic edition — may be a string or a list; take first element
        ee_raw = info.get("ee")
        if isinstance(ee_raw, list):
            ee = ee_raw[0] if ee_raw else None
        else:
            ee = ee_raw or None

        # pdf_url: set when ee is a direct PDF or an arXiv PDF link
        pdf_url: str | None = None
        if ee and (ee.endswith(".pdf") or "arxiv.org/pdf" in ee):
            pdf_url = ee

        # is_open_access: True if we have a PDF URL or ee links to arXiv
        is_open_access = pdf_url is not None or (ee is not None and "arxiv.org" in ee)

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            abstract=None,
            journal=journal,
            url=url,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=is_open_access,
        )
