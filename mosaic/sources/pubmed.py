"""PubMed / NCBI E-utilities search source."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import parse_authors_name_key, parse_year_earliest
from mosaic.sources.base import BaseSource, build_field_query, extract_year_range

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


class PubMedSource(BaseSource):
    """Search PubMed via NCBI E-utilities (esearch + esummary).

    No API key is required.  Providing one raises the rate limit from
    3 req/s to 10 req/s and should be preferred in high-volume usage.
    Configure via ``mosaic config --ncbi-key YOUR_KEY``.
    """

    name = "PubMed"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def available(self) -> bool:
        return True

    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Search PubMed using the NCBI E-utilities two-step flow.

        First calls ``esearch`` to retrieve a list of PMIDs matching the
        query, then calls ``esummary`` to fetch metadata for those PMIDs.
        Native support for title/abstract field scoping, author, journal,
        and year filters using PubMed query tags.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results (capped at 10 000,
                the NCBI E-utilities hard limit for esearch).
            filters: Optional filters; ``raw_query`` overrides the default
                mapping when set.

        Returns:
            A list of Paper objects parsed from the esummary response.
        """
        # ── build PubMed query ─────────────────────────────────────────
        pm_query = build_field_query(query, filters, "{}[ti]", "{}[ab]")

        if filters:
            if filters.authors:
                for author in filters.authors:
                    pm_query += f' AND "{author}"[au]'
            if filters.journal:
                pm_query += f' AND "{filters.journal}"[ta]'

        # ── step 1: esearch → PMIDs ────────────────────────────────────
        params: dict = {
            "db": "pubmed",
            "term": pm_query,
            "retmax": min(max_results, 10_000),
            "retmode": "json",
        }

        # Date filtering: use mindate/maxdate API params rather than
        # embedding [pdat] in the query string — far more reliable.
        if filters:
            y_from, y_to = extract_year_range(filters)
            if y_from or y_to:
                params["datetype"] = "pdat"
                params["mindate"] = str(y_from or y_to)
                params["maxdate"] = str(y_to or y_from)
        if self._api_key:
            params["api_key"] = self._api_key

        with httpx.Client(timeout=30) as client:
            resp = client.get(_ESEARCH, params=params)
            resp.raise_for_status()
            pmids = resp.json().get("esearchresult", {}).get("idlist", [])
            if not pmids:
                return []

            # ── step 2: esummary → metadata (POST avoids URL-length limits) ──
            sum_data: dict = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
            }
            if self._api_key:
                sum_data["api_key"] = self._api_key

            resp2 = client.post(_ESUMMARY, data=sum_data, timeout=60)
            resp2.raise_for_status()
            result = resp2.json().get("result", {})

        return [self._parse(result[pmid]) for pmid in pmids if pmid in result]

    def _parse(self, item: dict) -> Paper:
        """Parse a single esummary result dict into a Paper.

        Args:
            item: A dict from the ``result`` map of the esummary response,
                keyed by PMID.  Contains fields such as ``title``,
                ``authors``, ``pubdate``, ``fulljournalname``, ``volume``,
                ``issue``, ``pages``, and ``articleids``.

        Returns:
            A Paper with ``is_open_access=True`` and a PMC PDF URL when a
            PMC ID is present in the ``articleids`` list.
        """
        # authors
        authors = parse_authors_name_key(item.get("authors") or [])

        # year: prefer the earliest of pubdate and epubdate so that the year
        # shown is consistent with PubMed's pdat filter (which uses epubdate
        # for epub-ahead-of-print articles).
        # Both fields can be "2021 Jan 15", "2021 Jan", "2021", "2021 Winter".
        year = parse_year_earliest(item, ["epubdate", "pubdate"])

        # extract DOI and PMC ID from articleids list
        doi: str | None = None
        pmcid: str | None = None
        for aid in item.get("articleids") or []:
            idtype = aid.get("idtype", "")
            value = aid.get("value", "")
            if idtype == "doi" and value:
                doi = value
            elif idtype == "pmc" and value:
                pmcid = value  # e.g. "PMC12345"

        is_oa = bool(pmcid)
        pdf_url: str | None = None
        if pmcid:
            pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"

        pmid = str(item.get("uid") or "")
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

        return Paper(
            title=item.get("title") or "",
            authors=authors,
            year=year,
            doi=doi,
            abstract=None,  # esummary does not include abstracts
            journal=item.get("fulljournalname") or item.get("source") or None,
            volume=item.get("volume") or None,
            issue=item.get("issue") or None,
            pages=item.get("pages") or None,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=is_oa,
            url=url,
        )
