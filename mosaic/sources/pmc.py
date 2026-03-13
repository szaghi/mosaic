"""PubMed Central (PMC) full-text search source via NCBI E-utilities."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_ESEARCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


class PMCSource(BaseSource):
    """Search PubMed Central via NCBI E-utilities (esearch + esummary, db=pmc).

    Every result is open access and carries a direct PDF URL constructed
    from its numeric PMC ID.  The same NCBI API key used for PubMed applies
    here; configure it once with ``mosaic config --ncbi-key YOUR_KEY``.
    """

    name = "PubMed Central"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        """Search PubMed Central using the NCBI E-utilities two-step flow.

        First calls ``esearch`` (db=pmc) to retrieve a list of numeric PMC IDs,
        then calls ``esummary`` to fetch metadata for those records.  Native
        support for title/abstract field scoping, author, journal, and year
        filters using PubMed query tags.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results (capped at 10 000,
                the NCBI E-utilities hard limit for esearch).
            filters: Optional filters; ``raw_query`` overrides the default
                mapping when set.

        Returns:
            A list of Paper objects parsed from the esummary response; all
            results have ``is_open_access=True`` and a direct PDF URL.
        """
        # ── build query (same PMC/PubMed tag syntax) ───────────────────
        if filters and filters.raw_query:
            pmc_query = filters.raw_query
        elif filters and filters.field == "title":
            pmc_query = f"{query}[ti]"
        elif filters and filters.field == "abstract":
            pmc_query = f"{query}[ab]"
        else:
            pmc_query = query

        if filters:
            if filters.authors:
                for author in filters.authors:
                    pmc_query += f' AND "{author}"[au]'
            if filters.journal:
                pmc_query += f' AND "{filters.journal}"[ta]'

        # ── step 1: esearch (db=pmc) → numeric PMC IDs ─────────────────
        params: dict = {
            "db": "pmc",
            "term": pmc_query,
            "retmax": min(max_results, 10_000),
            "retmode": "json",
        }

        # Date filtering: use mindate/maxdate API params rather than
        # embedding [pdat] in the query string — far more reliable.
        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                params["datetype"] = "pdat"
                params["mindate"]  = str(y_from or y_to)
                params["maxdate"]  = str(y_to   or y_from)
        if self._api_key:
            params["api_key"] = self._api_key

        resp = httpx.get(_ESEARCH, params=params, timeout=30)
        resp.raise_for_status()
        pmc_ids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not pmc_ids:
            return []

        # ── step 2: esummary (db=pmc) → metadata (POST avoids URL-length limits)
        sum_data: dict = {
            "db": "pmc",
            "id": ",".join(pmc_ids),
            "retmode": "json",
        }
        if self._api_key:
            sum_data["api_key"] = self._api_key

        resp2 = httpx.post(_ESUMMARY, data=sum_data, timeout=60)
        resp2.raise_for_status()
        result = resp2.json().get("result", {})

        return [self._parse(result[uid]) for uid in pmc_ids if uid in result]

    def _parse(self, item: dict) -> Paper:
        """Parse a single PMC esummary result dict into a Paper.

        Args:
            item: A dict from the ``result`` map of the PMC esummary response,
                keyed by numeric PMC ID.  Contains fields such as ``title``,
                ``authors``, ``pubdate``, ``fulljournalname``, ``volume``,
                ``issue``, ``pages``, and ``articleids``.

        Returns:
            A Paper with ``is_open_access=True`` and a direct PMC PDF URL
            built from the numeric ``uid``.
        """
        authors = [a.get("name", "") for a in (item.get("authors") or [])]

        # year: prefer the earliest of pubdate and epubdate (see PubMedSource).
        year: int | None = None
        for field in ("epubdate", "pubdate"):
            raw = str(item.get(field) or "")
            if raw:
                part = raw.split()[0]
                if part.isdigit() and len(part) == 4:
                    y = int(part)
                    if year is None or y < year:
                        year = y

        # extract DOI from articleids list
        doi: str | None = None
        for aid in item.get("articleids") or []:
            if aid.get("idtype") == "doi" and aid.get("value"):
                doi = aid["value"]
                break

        uid = str(item.get("uid") or "")
        pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{uid}/pdf/" if uid else None
        url     = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{uid}/"    if uid else None

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
            is_open_access=True,  # PMC is an open-access archive by definition
            url=url,
        )
