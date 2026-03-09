"""Zenodo open-access research repository API source."""
from __future__ import annotations
import re
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

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
        if filters and filters.raw_query:
            q = filters.raw_query
        elif filters and filters.field == "title":
            q = f"title:{query}"
        elif filters and filters.field == "abstract":
            q = f"description:{query}"
        else:
            q = query

        # year filter
        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                y_lo = f"{y_from or y_to}-01-01"
                y_hi = f"{y_to or y_from}-12-31"
                q += f" AND publication_date:[{y_lo} TO {y_hi}]"
            if filters.authors:
                for author in filters.authors:
                    q += f' AND creators.name:"{author}"'
            if filters.journal:
                q += f' AND journal.title:"{filters.journal}"'

        params: dict = {
            "q": q,
            "size": min(max_results, 100),
            "type": "publication",
            "sort": "bestmatch",
        }
        if self._token:
            params["access_token"] = self._token

        resp = httpx.get(_BASE, params=params, timeout=30)
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
            A Paper with all open-access Zenodo records marked as OA.
            PDF URL is set when a ``.pdf`` file entry is found in ``files``.
        """
        meta = hit.get("metadata", {})

        title = meta.get("title", "")

        creators = meta.get("creators") or []
        authors = [c.get("name", "") for c in creators]

        pub_date = meta.get("publication_date") or ""
        year: int | None = None
        if pub_date:
            m = re.match(r"(\d{4})", pub_date)
            if m:
                year = int(m.group(1))

        doi = meta.get("doi") or None

        # description may contain HTML — strip tags for a plain-text abstract
        raw_desc = meta.get("description") or ""
        abstract = re.sub(r"<[^>]+>", " ", raw_desc).strip() or None

        journal_info = meta.get("journal") or {}
        journal = journal_info.get("title") or None

        url = hit.get("links", {}).get("html") or None

        # PDF: first file entry whose key ends with .pdf
        pdf_url: str | None = None
        for f in (hit.get("files") or []):
            if str(f.get("key", "")).lower().endswith(".pdf"):
                pdf_url = f.get("links", {}).get("self") or None
                break

        # all Zenodo records are open access by definition
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
