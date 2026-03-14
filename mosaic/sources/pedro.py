"""PEDro — Physiotherapy Evidence Database source (HTML scraping)."""

from __future__ import annotations

import re
import time

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_SESSION_URL = "https://search.pedro.org.au/advanced-search"
_SEARCH_URL = "https://search.pedro.org.au/advanced-search/results"
_BASE_URL = "https://search.pedro.org.au"

# Default delay between HTTP requests (seconds).  PEDro's fair-use policy
# prohibits automated bulk downloads; 3 s is a conservative safe-fair value.
_DEFAULT_DELAY = 3.0

_RESULTS_PER_PAGE = 25


class PEDroSource(BaseSource):
    """Search PEDro via its HTML advanced-search form.

    PEDro indexes RCTs, systematic reviews, and clinical practice guidelines
    in physiotherapy (~67 000 records, independently quality-rated with the
    PEDro Scale).

    .. warning::
        PEDro's `Fair Use policy <https://pedro.org.au/fair-use/>`_ prohibits
        automated bulk downloading.  This source must be explicitly opted into
        by setting ``sources.pedro.acknowledge_fair_use = true`` in the config,
        confirming that you will only use it for small, targeted queries.

    Rate limiting is enforced between every HTTP request.  The default delay
    (``sources.pedro.rate_limit_delay``, default ``3.0`` s) is set to a
    conservative safe-fair value.  You may lower it, but only if you have
    confirmed that your usage remains within PEDro's acceptable-use terms.

    The search-result listing does not include authors, year, DOI, or abstract.
    Set ``sources.pedro.fetch_details = true`` (or pass ``--pedro-fetch-details``
    to ``mosaic config``) to fetch each record's detail page and populate those
    fields.  This issues one extra HTTP request per result, so with the default
    3 s delay a 25-result page will take roughly 75 s of additional wait time.

    CLI shorthand: ``pedro``
    """

    name = "PEDro"

    def __init__(
        self,
        *,
        acknowledge_fair_use: bool = False,
        rate_limit_delay: float = _DEFAULT_DELAY,
        fetch_details: bool = False,
    ) -> None:
        self._enabled = acknowledge_fair_use
        self._delay = rate_limit_delay
        self._fetch_details = fetch_details

    def available(self) -> bool:
        """Return True only when the user has explicitly acknowledged the fair-use policy."""
        return self._enabled

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        """Search PEDro via the advanced-search form (GET parameters).

        The first request goes to the session-initialisation URL to obtain
        session cookies.  Subsequent search and pagination requests include
        those cookies automatically.

        Supported parameters:

        * ``abstract_with_title`` — general keyword search (default)
        * ``title``               — title-only (when ``--field title``)
        * ``year_of_publication`` — mapped from ``filters.year_from``
        * ``pg`` / ``page``       — pagination

        A configurable rate-limiting delay (``sources.pedro.rate_limit_delay``)
        is inserted between every HTTP request.

        Args:
            query: Free-text keyword query.
            max_results: Maximum number of results to return.
            filters: Optional filters.  ``field="title"`` switches to
                title-only search; ``year_from`` is forwarded as
                ``year_of_publication``.

        Returns:
            A list of Paper objects with title, method (as ``journal``),
            PEDro score (as a brief ``abstract`` note), and record URL
            populated.  Authors and year are ``[]`` / ``None`` because
            they require separate per-record requests.
        """
        search_field = "title" if (filters and filters.field == "title") else "abstract_with_title"
        params: dict[str, object] = {search_field: query, "pg": 1}

        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            if y_from:
                params["year_of_publication"] = y_from

        with httpx.Client(
            headers={
                "User-Agent": (
                    "MOSAIC (non-commercial research tool; https://github.com/szaghi/mosaic)"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=30,
        ) as client:
            # Initialise session — required for PEDro's search to return results
            client.get(_SESSION_URL)
            time.sleep(self._delay)

            papers: list[Paper] = []
            page = 1

            while len(papers) < max_results:
                if page > 1:
                    params["page"] = page
                    time.sleep(self._delay)

                resp = client.get(_SEARCH_URL, params=params)
                resp.raise_for_status()

                new_papers = self._parse_page(resp.text)
                if not new_papers:
                    break

                papers.extend(new_papers)
                if len(new_papers) < _RESULTS_PER_PAGE:
                    # Last page — no need to fetch more
                    break
                page += 1

            papers = papers[:max_results]

            if self._fetch_details:
                for i, paper in enumerate(papers):
                    if paper.url:
                        time.sleep(self._delay)
                        try:
                            detail_resp = client.get(paper.url)
                            detail_resp.raise_for_status()
                            papers[i] = self._enrich_from_detail(paper, detail_resp.text)
                        except Exception:
                            pass  # keep partial data on failure

        if filters:
            papers = [p for p in papers if filters.match(p)]

        return papers

    @staticmethod
    def _parse_page(html: str) -> list[Paper]:
        """Parse Paper objects from a PEDro search-results HTML page.

        The relevant table structure is::

            <table class="search-results">
              <tbody>
                <tr>
                  <td>
                    <a href=".../record-detail/{id}" class="left">{title}</a>
                  </td>
                  <td>{method}</td>       <!-- e.g. "clinical trial" -->
                  <td>{score}</td>        <!-- e.g. "7/10" or "N/A" -->
                  <td class="hidden-narrow">...</td>
                </tr>
              </tbody>
            </table>

        Args:
            html: Raw HTML text of the search-results page.

        Returns:
            List of Paper objects extracted from the table rows.
        """
        papers: list[Paper] = []

        tbody_m = re.search(
            r'<table[^>]+class="search-results"[^>]*>(.*?)</table>',
            html,
            re.DOTALL,
        )
        if not tbody_m:
            return papers

        tbody = tbody_m.group(1)

        row_re = re.compile(
            r'<td><a href="(?P<url>[^"]+record-detail/(?P<rid>\d+)[^"]*)"[^>]*>'
            r"(?P<title>[^<]+)</a></td>"
            r"\s*<td>(?P<method>[^<]*)</td>"
            r"\s*<td>(?P<score>[^<]*)</td>",
            re.DOTALL,
        )

        for m in row_re.finditer(tbody):
            title = _unescape(m.group("title").strip())
            if not title:
                continue

            url = m.group("url")
            if not url.startswith("http"):
                url = f"{_BASE_URL}{url}"

            method = m.group("method").strip()
            score_raw = m.group("score").strip()

            note_parts: list[str] = []
            if method:
                note_parts.append(f"Method: {method}")
            if score_raw and score_raw != "N/A":
                note_parts.append(f"PEDro score: {score_raw}")
            abstract = "; ".join(note_parts) if note_parts else None

            papers.append(
                Paper(
                    title=title,
                    authors=[],
                    year=None,
                    doi=None,
                    abstract=abstract,
                    journal=method.title() if method else None,
                    source="PEDro",
                    is_open_access=False,
                    url=url,
                )
            )

        return papers

    @staticmethod
    def _parse_detail_page(html: str) -> dict:
        """Extract authors, year, DOI, abstract, and journal from a PEDro record page.

        PEDro detail pages use a bare ``<table>`` with positional ``<tr><td>`` rows
        and no class names:

        * row 0 — title (``<strong>``)
        * row 1 — authors as plain text, affiliation in trailing ``[...]``
        * row 2 — citation: "Journal Name YYYY Mon;vol(issue):pages"
        * row 3 — method type
        * row 4 — abstract text followed by full-text links

        DOI appears as ``<a href="https://dx.doi.org/...">DOI</a>`` inside row 4.

        Returns a dict with keys: authors (list[str]), year (int|None),
        doi (str|None), abstract (str|None), journal (str|None).
        """
        result: dict = {"authors": [], "year": None, "doi": None, "abstract": None, "journal": None}

        # Extract all <td>…</td> cell contents in document order
        td_re = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
        cells = [m.group(1) for m in td_re.finditer(html)]

        def _text(raw: str) -> str:
            return _unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip())

        # Row 1 — authors
        if len(cells) > 1:
            authors_raw = _text(cells[1])
            # Strip trailing affiliation like "[Ottawa Panel]"
            authors_raw = re.sub(r"\s*\[.*?\]\s*$", "", authors_raw).strip()
            if authors_raw:
                # Split on ", " only where the next token starts with an uppercase letter
                result["authors"] = [
                    a.strip() for a in re.split(r",\s*(?=[A-Z])", authors_raw) if a.strip()
                ]

        # Row 2 — citation: "Journal Name 2019 Sep;49(9):CPG1-CPG95"
        if len(cells) > 2:
            citation = _text(cells[2])
            if citation:
                y_m = re.search(r"\b(19|20)\d{2}\b", citation)
                if y_m:
                    result["year"] = int(y_m.group())
                    # Journal is everything before the year
                    result["journal"] = citation[: y_m.start()].rstrip(" ,;") or None

        # Row 4 — abstract (stop before the "Full text…" sentence)
        if len(cells) > 4:
            abstract_raw = cells[4]
            # Truncate at the "Full text" marker before stripping tags
            abstract_raw = re.split(r"Full text", abstract_raw, maxsplit=1)[0]
            abstract = _text(abstract_raw)
            result["abstract"] = abstract or None

        # DOI — from the dx.doi.org link present in row 4 (or anywhere on page)
        doi_m = re.search(r'https?://(?:dx\.)?doi\.org/([^\s"<]+)', html)
        if doi_m:
            result["doi"] = doi_m.group(1).rstrip(".")

        return result

    @classmethod
    def _enrich_from_detail(cls, paper: Paper, html: str) -> Paper:
        """Return a new Paper with metadata from the detail page merged in."""
        detail = cls._parse_detail_page(html)
        return Paper(
            title=paper.title,
            authors=detail["authors"] or paper.authors,
            year=detail["year"] or paper.year,
            doi=detail["doi"] or paper.doi,
            abstract=detail["abstract"] or paper.abstract,
            journal=detail["journal"] or paper.journal,
            source=paper.source,
            is_open_access=paper.is_open_access,
            url=paper.url,
        )


def _unescape(s: str) -> str:
    """Decode common HTML entities in title text."""
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
        .replace("&apos;", "'")
    )
