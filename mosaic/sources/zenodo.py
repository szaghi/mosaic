"""Zenodo open-access research repository API source."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import normalise_doi, parse_authors_name_key, parse_year, strip_html
from mosaic.sources.base import (
    BaseSource,
    any_of,
    build_field_query,
    extract_year_range,
    lucene_phrase,
    with_retry,
)

_BASE = "https://zenodo.org/api/records"


class ZenodoSource(BaseSource):
    """Search source for Zenodo, CERN's open-access research repository.

    Zenodo hosts 3 million+ open research outputs from CERN and EU-funded
    projects, including papers, datasets, software, posters, and theses.
    No authentication is required; an optional access token raises rate limits
    from 60 to 100+ requests per minute.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "Zenodo"

    def __init__(self, api_key: str = "") -> None:
        """Initialise the Zenodo source.

        Args:
            api_key: Optional Zenodo personal access token obtained at
                https://zenodo.org/account/settings/applications/tokens/new/.
                The source works without a key at a lower rate limit.
        """
        self._token = api_key

    def available(self) -> bool:
        """Return True — Zenodo requires no credentials.

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
        """Search the Zenodo records endpoint.

        Translates the query into Zenodo's Elasticsearch query syntax, scoping
        to ``title:`` or ``description:`` fields when requested. Author,
        journal, and year constraints are appended as field clauses. Results
        are limited to ``resource_type.type:publication`` so datasets and
        software are excluded.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping, authors, journal, and
                year range or specific years. ``raw_query`` overrides the
                default mapping if set.

        Returns:
            A list of Paper objects parsed from the ``hits.hits`` array.
        """
        q = build_field_query(query, filters, "title:{}", "description:{}", phrase=True)

        # year filter
        if filters:
            y_from, y_to = extract_year_range(filters)
            if y_from or y_to:
                y_lo = f"{y_from or y_to}-01-01"
                y_hi = f"{y_to or y_from}-12-31"
                q += f" AND publication_date:[{y_lo} TO {y_hi}]"
            if filters.authors:
                q += " AND " + any_of(map(lucene_phrase, filters.authors), "creators.name:{}")
            if filters.journal:
                q += f" AND journal.title:{lucene_phrase(filters.journal)}"

        params: dict = {
            "q": q,
            "size": min(max_results, 100),
            "type": "publication",
            "sort": "bestmatch",
        }
        # Send the token as a header, never in the URL: httpx error messages
        # embed the full URL and would otherwise leak it.
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}

        with httpx.Client(timeout=30, headers=headers) as client:
            resp = with_retry(lambda: client.get(_BASE, params=params))
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", [])
        return [self._parse(hit) for hit in hits]

    def _parse(self, hit: dict) -> Paper:
        """Parse a single Zenodo record dict into a Paper.

        Args:
            hit: A dict from the Zenodo ``hits.hits`` array, containing a
                ``metadata`` sub-dict with ``title``, ``creators``,
                ``publication_date``, ``doi``, ``description``,
                ``journal``, and optionally a ``files`` list.

        Returns:
            A Paper marked as OA when ``metadata.access_right`` is ``"open"``
            (or absent).  PDF URL is set when a ``.pdf`` file entry is found
            in ``files`` of an open record.
        """
        meta = hit.get("metadata", {})

        title = meta.get("title", "")

        authors = parse_authors_name_key(meta.get("creators") or [])

        year = parse_year(meta.get("publication_date"))

        doi = normalise_doi(meta.get("doi"))

        # description may contain HTML — strip tags for a plain-text abstract
        abstract = strip_html(meta.get("description"))

        journal_info = meta.get("journal") or {}
        journal = journal_info.get("title") or None

        url = hit.get("links", {}).get("html") or None

        # Zenodo also hosts embargoed, restricted and closed records; only
        # "open" ones have publicly downloadable files.
        is_oa = (meta.get("access_right") or "open") == "open"

        # PDF: first file entry whose key ends with .pdf
        pdf_url: str | None = None
        if is_oa:
            for f in hit.get("files") or []:
                if str(f.get("key", "")).lower().endswith(".pdf"):
                    pdf_url = f.get("links", {}).get("self") or None
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
            is_open_access=is_oa,
        )
