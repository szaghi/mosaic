"""NASA Astrophysics Data System (ADS) API source."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import extract_first, parse_year
from mosaic.sources.base import BaseSource, build_field_query, extract_year_range

_BASE = "https://api.adsabs.harvard.edu/v1/search/query"
_FIELDS = "title,author,year,doi,abstract,bibcode,identifier,pub,property"


class NASAADSSource(BaseSource):
    """Search source for the NASA Astrophysics Data System (ADS).

    ADS covers 15 million+ records in astronomy, astrophysics, planetary
    science, physics, and geosciences. It provides strong open-access PDF
    access via arXiv mirrors and publisher agreements.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "NASA ADS"

    def __init__(self, api_key: str = "") -> None:
        """Initialise the NASA ADS source.

        Args:
            api_key: A NASA ADS API token obtained free of charge from
                https://ui.adsabs.harvard.edu/user/settings/token.
                The source is disabled when this is empty.
        """
        self._api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def available(self) -> bool:
        """Return True only when a NASA ADS API token has been configured.

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
        """Search the NASA ADS search endpoint.

        Translates the query into ADS query syntax, scoping to ``title:`` or
        ``abstract:`` fields when requested and appending a ``year:YYYY-YYYY``
        clause for year range filters.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 200).
            filters: Optional filters for field scoping and year range.
                ``raw_query`` overrides the default mapping if set. Author
                and journal filters are applied as post-processing by the
                framework (ADS field syntax is complex and varies by record).

        Returns:
            A list of Paper objects parsed from the ``response.docs`` array.
        """
        ads_query = build_field_query(query, filters, "title:{}", "abstract:{}")

        if filters:
            y_from, y_to = extract_year_range(filters)
            if y_from or y_to:
                ads_query += f" year:{y_from or y_to}-{y_to or y_from}"

        with httpx.Client(timeout=30, headers=self._headers) as client:
            resp = client.get(
                _BASE,
                params={
                    "q": ads_query,
                    "fl": _FIELDS,
                    "rows": min(max_results, 200),
                    "sort": "score desc",
                },
            )
            resp.raise_for_status()
            docs = resp.json().get("response", {}).get("docs", [])
        return [self._parse(doc) for doc in docs]

    def _parse(self, doc: dict) -> Paper:
        """Parse a single ADS document dict into a Paper.

        Args:
            doc: A dict from the ADS ``response.docs`` array containing
                fields such as ``title`` (list), ``author`` (list), ``year``
                (str), ``doi`` (list), ``abstract`` (str), ``bibcode`` (str),
                ``identifier`` (list), ``pub`` (str), and ``property`` (list).

        Returns:
            A Paper with a URL pointing to the ADS abstract page for the
            bibcode, and a PDF URL constructed from the bibcode when the
            article is open access.
        """
        # title is a list in ADS
        title = extract_first(doc.get("title")) or ""

        authors = list(doc.get("author") or [])

        year = parse_year(doc.get("year"))

        doi = extract_first(doc.get("doi"))

        abstract = doc.get("abstract") or None

        bibcode = doc.get("bibcode") or ""
        url = f"https://ui.adsabs.harvard.edu/abs/{bibcode}" if bibcode else None

        # extract arXiv ID from the identifier list (e.g. "arXiv:2301.xxxxx")
        arxiv_id: str | None = None
        for ident in doc.get("identifier") or []:
            if ident.startswith("arXiv:"):
                arxiv_id = ident[len("arXiv:") :]
                break

        journal = doc.get("pub") or None

        property_list = doc.get("property") or []
        is_oa = "OPENACCESS" in property_list

        pdf_url: str | None = None
        if bibcode and is_oa:
            pdf_url = f"https://ui.adsabs.harvard.edu/link_gateway/{bibcode}/PUB_PDF"

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            abstract=abstract,
            journal=journal,
            url=url,
            arxiv_id=arxiv_id,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=is_oa,
        )
