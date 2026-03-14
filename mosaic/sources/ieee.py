"""IEEE Xplore API source.

Uses the official IEEE Xplore REST API, which requires a free API key and
provides access to IEEE journals, transactions, magazines, and conference
proceedings. The source is disabled when ``api_key`` is empty.
"""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import parse_authors_name_key
from mosaic.sources.base import BaseSource, build_field_query, extract_year_range

_BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


class IEEEXploreSource(BaseSource):
    """Search source for the IEEE Xplore digital library.

    Covers 5 million+ articles from IEEE journals, transactions, magazines,
    and conference proceedings. Requires a free API key registered at
    https://developer.ieee.org. Open-access articles include a direct PDF
    link from the ``pdf_url`` field.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "IEEE Xplore"

    def __init__(self, api_key: str = "") -> None:
        """Initialise the IEEE Xplore API source.

        Args:
            api_key: A IEEE Xplore API key obtained free of charge at
                https://developer.ieee.org. The source is disabled when
                this is empty.
        """
        self._api_key = api_key

    def available(self) -> bool:
        """Return True only when an IEEE Xplore API key has been configured.

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
        """Search the IEEE Xplore article search endpoint.

        Translates the query into IEEE Xplore query syntax, scoping to
        ``title:`` or ``abstract:`` when requested. Year constraints are
        sent as native ``start_year`` / ``end_year`` parameters. Author
        and journal filters are applied as post-processing by the framework.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 200).
            filters: Optional filters for field scoping and year range.
                ``raw_query`` overrides the default mapping if set. Author
                and journal filters are applied as post-processing.

        Returns:
            A list of Paper objects parsed from the ``articles`` array.
        """
        querytext = build_field_query(query, filters, 'title:"{}"', 'abstract:"{}"')

        params: dict = {
            "querytext": querytext,
            "max_records": min(max_results, 200),
            "apikey": self._api_key,
        }

        if filters:
            y_from, y_to = extract_year_range(filters)
            if y_from:
                params["start_year"] = y_from
            if y_to:
                params["end_year"] = y_to

        with httpx.Client(timeout=30) as client:
            resp = client.get(_BASE, params=params)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
        return [self._parse(item) for item in articles]

    def _parse(self, item: dict) -> Paper:
        """Parse a single IEEE Xplore article dict into a Paper.

        Args:
            item: A dict from the IEEE Xplore ``articles`` array, containing
                fields such as ``title`` (str), ``authors`` (dict with an
                ``authors`` list of ``{full_name: "First Last"}`` dicts),
                ``publication_year`` (int), ``doi`` (str), ``abstract`` (str),
                ``publication_title`` (str), ``access_type`` (str),
                ``pdf_url`` (str, OA articles only), and ``html_url`` (str).

        Returns:
            A Paper with ``is_open_access=True`` and a PDF URL when
            ``access_type`` is ``"OPEN_ACCESS"``.
        """
        title = item.get("title") or ""

        authors_wrapper = item.get("authors") or {}
        authors_list = authors_wrapper.get("authors") or []
        authors = parse_authors_name_key(authors_list, key="full_name")

        year_raw = item.get("publication_year")
        year: int | None = int(year_raw) if year_raw else None

        doi = item.get("doi") or None

        abstract = item.get("abstract") or None

        journal = item.get("publication_title") or None

        is_oa = item.get("access_type") == "OPEN_ACCESS"

        url = item.get("html_url") or None

        pdf_url: str | None = None
        if is_oa:
            pdf_url = item.get("pdf_url") or None

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
