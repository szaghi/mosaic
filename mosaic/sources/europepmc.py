"""Europe PubMed Central API."""

from __future__ import annotations

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import parse_year, split_authors
from mosaic.sources.base import BaseSource, build_field_query, extract_year_range

_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class EuropePMCSource(BaseSource):
    name = "Europe PMC"

    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Search the Europe PMC REST API.

        Builds a query using Europe PMC field qualifiers (``TITLE:``,
        ``ABSTRACT:``, ``AUTH:``, ``JOURNAL:``, ``PUB_YEAR:``). Requests the
        ``core`` result type to include abstracts.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping, authors, journal, and
                year range. ``raw_query`` overrides the default mapping if set.

        Returns:
            A list of Paper objects parsed from the ``resultList.result`` array.
        """
        epmc_query = build_field_query(query, filters, 'TITLE:"{}"', 'ABSTRACT:"{}"')
        if filters:
            if filters.authors:
                for author in filters.authors:
                    epmc_query += f' AND AUTH:"{author}"'
            if filters.journal:
                epmc_query += f' AND JOURNAL:"{filters.journal}"'
            y_from, y_to = extract_year_range(filters)
            if y_from or y_to:
                epmc_query += f" AND PUB_YEAR:[{y_from or y_to} TO {y_to or y_from}]"
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                _BASE,
                params={
                    "query": epmc_query,
                    "pageSize": min(max_results, 100),
                    "resultType": "core",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return [self._parse(item) for item in data.get("resultList", {}).get("result", [])]

    def _parse(self, item: dict) -> Paper:
        """Parse a single Europe PMC result dict into a Paper.

        Args:
            item: A dict from the Europe PMC ``result`` array containing
                fields such as ``title``, ``authorString``, ``pubYear``,
                ``doi``, ``abstractText``, ``journalTitle``, ``isOpenAccess``,
                and ``pmcid``.

        Returns:
            A Paper with a PDF URL constructed from the PMC ID when the
            article is open access and has a PMC identifier.
        """
        authors = split_authors(item.get("authorString") or "")

        year = parse_year(item.get("pubYear"))

        is_oa = item.get("isOpenAccess") == "Y"

        pdf_url = None
        pmcid = item.get("pmcid")
        if pmcid and is_oa:
            pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"

        return Paper(
            title=item.get("title") or "",
            authors=authors,
            year=year,
            doi=item.get("doi"),
            abstract=item.get("abstractText"),
            journal=item.get("journalTitle"),
            volume=item.get("journalVolume"),
            issue=item.get("issue"),
            pages=item.get("pageInfo"),
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=is_oa,
            url=f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id', '')}",
        )
