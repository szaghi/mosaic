"""NASA Astrophysics Data System (ADS) API source."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

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
        if filters and filters.raw_query:
            ads_query = filters.raw_query
        elif filters and filters.field == "title":
            ads_query = f"title:{query}"
        elif filters and filters.field == "abstract":
            ads_query = f"abstract:{query}"
        else:
            ads_query = query

        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                ads_query += f" year:{y_from or y_to}-{y_to or y_from}"

        resp = httpx.get(
            _BASE,
            params={
                "q": ads_query,
                "fl": _FIELDS,
                "rows": min(max_results, 200),
                "sort": "score desc",
            },
            headers=self._headers,
            timeout=30,
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
        title_raw = doc.get("title") or []
        title = title_raw[0] if title_raw else ""

        authors = list(doc.get("author") or [])

        year_str = str(doc.get("year") or "")
        year = int(year_str) if year_str.isdigit() else None

        doi_list = doc.get("doi") or []
        doi = doi_list[0] if doi_list else None

        abstract = doc.get("abstract") or None

        bibcode = doc.get("bibcode") or ""
        url = f"https://ui.adsabs.harvard.edu/abs/{bibcode}" if bibcode else None

        # extract arXiv ID from the identifier list (e.g. "arXiv:2301.xxxxx")
        arxiv_id: str | None = None
        for ident in (doc.get("identifier") or []):
            if ident.startswith("arXiv:"):
                arxiv_id = ident[len("arXiv:"):]
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
