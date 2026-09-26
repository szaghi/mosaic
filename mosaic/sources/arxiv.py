"""arXiv API source (no auth required, all OA)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import httpx

from mosaic.errors import SourceError
from mosaic.models import Paper, SearchFilters
from mosaic.parsing import normalise_doi
from mosaic.sources.base import (
    BaseSource,
    Throttle,
    any_of,
    build_field_query,
    extract_year_range,
    phrase_if_needed,
    user_agent,
    with_retry,
)

_BASE = "https://export.arxiv.org/api/query"
_ARXIV_RETRY_STATUSES = frozenset({406, 429, 503})
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# arXiv asks for at most one request every 3 seconds.  The throttle is shared
# by every ArxivSource instance because build_sources() creates a fresh one
# for each search.
_THROTTLE = Throttle()


class ArxivSource(BaseSource):
    name = "arXiv"

    def __init__(self, delay: float = 3.0):
        self._delay = delay

    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Query the arXiv Atom API and return matching papers.

        Enforces a minimum inter-request delay to comply with arXiv rate-limit
        guidelines. Applies field-specific prefixes (``ti:``, ``abs:``,
        ``all:``) and optional author/journal/date range filters before
        submitting the query.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request from the API.
            filters: Optional filters for field scoping, authors, journal,
                and year range. ``filters.raw_query`` overrides ``query``
                entirely if set.

        Returns:
            A list of Paper objects parsed from the Atom feed.
        """
        search_query = build_field_query(query, filters, "ti:{}", "abs:{}", "all:{}", phrase=True)
        if filters:
            if filters.authors:
                search_query += " AND " + any_of(
                    [phrase_if_needed(a) for a in filters.authors], "au:{}"
                )
            if filters.journal:
                search_query += f" AND jr:{phrase_if_needed(filters.journal)}"
            y_from, y_to = extract_year_range(filters)
            if y_from or y_to:
                d_from = f"{y_from or '0000'}01010000"
                d_to = f"{y_to or '9999'}12312359"
                search_query += f" AND submittedDate:[{d_from} TO {d_to}]"

        # Keep ":" literal as in the API documentation: the arXiv gateway has
        # been observed answering 406 to field prefixes encoded as "%3A".
        query_string = urlencode(
            {"search_query": search_query, "start": 0, "max_results": max_results}, safe=":"
        )
        _THROTTLE.wait(self._delay)
        with httpx.Client(timeout=30, headers={"User-Agent": user_agent()}) as client:
            # The gateway also answers 406 while throttling bursts: retry after
            # at least the documented 3-second interval.
            resp = with_retry(
                lambda: client.get(f"{_BASE}?{query_string}"),
                statuses=_ARXIV_RETRY_STATUSES,
                min_wait=max(self._delay, 3.0),
            )
        if resp.status_code == 406:
            raise SourceError(
                "arXiv is throttling requests from this address (HTTP 406); "
                "wait a few minutes before searching arXiv again"
            )
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        papers = []
        for entry in root.findall("atom:entry", _NS):
            papers.append(self._parse(entry))
        return papers

    def _parse(self, entry: ET.Element) -> Paper:
        """Parse a single Atom ``<entry>`` element into a Paper.

        Args:
            entry: An ``xml.etree.ElementTree.Element`` representing one arXiv
                result entry from the Atom feed.

        Returns:
            A Paper populated with title, authors, year, DOI, arXiv ID,
            abstract, journal reference, PDF URL, and open-access flag.
        """

        def txt(tag: str) -> str | None:
            el = entry.find(tag, _NS)
            return el.text.strip() if el is not None and el.text else None

        arxiv_id = (txt("atom:id") or "").split("/abs/")[-1]
        authors = [
            a.findtext("atom:name", namespaces=_NS) or "" for a in entry.findall("atom:author", _NS)
        ]
        published = txt("atom:published") or ""
        year = int(published[:4]) if published else None

        pdf_url = None
        for link in entry.findall("atom:link", _NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")

        doi_el = entry.find("arxiv:doi", _NS)
        # Fall back to the canonical arXiv preprint DOI (strip version suffix).
        # Only a trailing "v<N>" is a version: old-style IDs such as
        # "solv-int/9901001v1" contain other "v"s.
        _arxiv_id_base = re.sub(r"v\d+$", "", arxiv_id)
        doi = normalise_doi(doi_el.text if doi_el is not None else None) or (
            f"10.48550/arXiv.{_arxiv_id_base}"
        )

        journal_el = entry.find("arxiv:journal_ref", _NS)
        journal = journal_el.text.strip() if journal_el is not None and journal_el.text else None

        return Paper(
            title=txt("atom:title") or "",
            authors=[a for a in authors if a],
            year=year,
            doi=doi,
            arxiv_id=arxiv_id,
            abstract=txt("atom:summary"),
            journal=journal,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=True,
            url=f"https://arxiv.org/abs/{arxiv_id}",
        )
