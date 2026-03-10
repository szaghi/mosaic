"""bioRxiv / medRxiv preprint source."""
from __future__ import annotations

import re
import urllib.parse

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE_API = "https://api.biorxiv.org/details"
# Extract DOI (without version suffix) from href="/content/10.1101/..."
_DOI_HREF_RE = re.compile(
    r'href="/content/(10\.1101/\d{4}\.\d{2}\.\d{2}\.\d+)(?:v\d+)?"'
)


class BioRxivSource(BaseSource):
    """bioRxiv and medRxiv preprint source.

    Queries both servers via the website search endpoint (which supports
    full keyword, author, and date-range search), then fetches complete
    metadata — including abstracts and PDF links — from the official
    ``api.biorxiv.org`` content API.

    All bioRxiv/medRxiv preprints are open access.  PDF URLs are
    constructed as ``https://www.{server}.org/content/{doi}v{n}.full.pdf``.

    The shorthand for ``--source`` is ``rxiv``.
    """

    name = "bioRxiv/medRxiv"

    def available(self) -> bool:
        return True

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        """Search bioRxiv and medRxiv for preprints matching *query*.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to return per server.
            filters: Optional filters applied to year, author, journal, and
                field scoping.  Year range and author filters are forwarded
                to the search URL as native bioRxiv query operators.

        Returns:
            A list of ``Paper`` objects (always ``is_open_access=True``).
        """
        search_query = self._build_query(query, filters)
        papers: list[Paper] = []
        for server in ("biorxiv", "medrxiv"):
            try:
                papers.extend(self._search_server(server, search_query, max_results))
            except Exception:
                continue
        # Post-process: author / journal filters (not supported natively)
        if filters:
            papers = [p for p in papers if filters.match(p)]
        return papers[:max_results]

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_query(query: str, filters: SearchFilters | None) -> str:
        """Append bioRxiv search operators for year and author filters."""
        if filters and filters.raw_query:
            return filters.raw_query
        parts = [query]
        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from:
                parts.append(f"after:{y_from - 1}-12-31")
            if y_to:
                parts.append(f"before:{y_to + 1}-01-01")
            for author in filters.authors:
                last = author.split()[-1] if author.split() else author
                parts.append(f"author1:{last}")
        return " ".join(parts)

    def _search_server(
        self,
        server: str,
        query: str,
        max_results: int,
    ) -> list[Paper]:
        encoded = urllib.parse.quote(query, safe="")
        url = (
            f"https://www.{server}.org/search/"
            f"{encoded}%20numresults%3A{max_results}%20sort%3Arelevance-rank"
        )
        resp = httpx.get(
            url,
            headers={"User-Agent": "MOSAIC/1.0"},
            timeout=30,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []

        # Extract unique DOIs from the search-result page
        seen: set[str] = set()
        dois: list[str] = []
        for m in _DOI_HREF_RE.finditer(resp.text):
            doi = m.group(1)
            if doi not in seen:
                seen.add(doi)
                dois.append(doi)
                if len(dois) >= max_results:
                    break

        papers = []
        for doi in dois:
            paper = self._fetch_paper(server, doi)
            if paper is not None:
                papers.append(paper)
        return papers

    def _fetch_paper(self, server: str, doi: str) -> Paper | None:
        """Fetch metadata for a single preprint from the bioRxiv content API."""
        url = f"{_BASE_API}/{server}/{doi}/0/json"
        try:
            resp = httpx.get(url, timeout=15)
            if resp.status_code != 200:
                return None
            items = resp.json().get("collection", [])
        except Exception:
            return None
        if not items:
            return None
        # items are ordered oldest→newest; take the latest version
        return self._parse(items[-1], server)

    def _parse(self, item: dict, server: str) -> Paper:
        doi = item.get("doi") or ""
        date_str = item.get("date") or ""   # "YYYY-MM-DD"
        year: int | None = None
        if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
            year = int(date_str[:4])

        version = str(item.get("version") or "1")
        pdf_url = (
            f"https://www.{server}.org/content/{doi}v{version}.full.pdf"
            if doi else None
        )

        authors_str = item.get("authors") or ""
        # bioRxiv API returns authors semicolon-separated: "Smith J; Jones A"
        authors = [a.strip() for a in re.split(r"[;]", authors_str) if a.strip()]

        category = item.get("category") or ""
        journal = f"{server.capitalize()} [{category}]" if category else server.capitalize()

        return Paper(
            title=(item.get("title") or "").strip(),
            authors=authors,
            year=year,
            doi=doi or None,
            abstract=item.get("abstract") or None,
            journal=journal,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=True,
            url=f"https://www.{server}.org/content/{doi}" if doi else None,
        )
