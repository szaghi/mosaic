"""Elsevier ScienceDirect API (open access only by default)."""

from __future__ import annotations

import re

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import normalise_doi, parse_year
from mosaic.sources.base import BaseSource, with_retry

_SEARCH = "https://api.elsevier.com/content/search/sciencedirect"
_ARTICLE = "https://api.elsevier.com/content/article/doi/{doi}"

_VOLUME_RE = re.compile(r"\bVol(?:ume|\.)?\s*([^,\s]+)", re.IGNORECASE)
_ISSUE_RE = re.compile(r"\b(?:Issue|No\.?)\s*([^,\s]+)", re.IGNORECASE)


def _split_volume_issue(raw: str | None) -> tuple[str | None, str | None]:
    """Split ScienceDirect's ``volumeIssue`` ("Volume 12, Issue 3") into parts.

    >>> _split_volume_issue("Volume 12, Issue 3")
    ('12', '3')
    >>> _split_volume_issue("Volume 45")
    ('45', None)
    >>> _split_volume_issue("Supplement")
    ('Supplement', None)
    """
    if not raw:
        return None, None
    vol_m = _VOLUME_RE.search(raw)
    issue_m = _ISSUE_RE.search(raw)
    volume = vol_m.group(1) if vol_m else None
    issue = issue_m.group(1) if issue_m else None
    if volume is None and issue is None:
        return raw.strip() or None, None
    return volume, issue


class ScienceDirectSource(BaseSource):
    name = "ScienceDirect"

    def __init__(self, api_key: str = "", inst_token: str = "", open_access_only: bool = True):
        self._api_key = api_key
        self._inst_token = inst_token
        self._oa_only = open_access_only

    def available(self) -> bool:
        """Return True only when an Elsevier API key has been configured."""
        return bool(self._api_key)

    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Search the Elsevier ScienceDirect full-text API.

        Builds a PUT request with a JSON body using Elsevier's query syntax
        (``TITLE(...)``, ``ABS(...)``). Optionally restricts to open-access
        articles. Author, journal, and date range filters are applied when
        present in ``filters``.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results (capped at 100).
            filters: Optional filters for field scoping (title/abstract),
                authors, journal, and year range. ``raw_query`` overrides
                the default field mapping if set.

        Returns:
            A list of Paper objects parsed from the ``results`` array.
        """
        headers = {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/json",
        }
        if self._inst_token:
            headers["X-ELS-Insttoken"] = self._inst_token

        if filters and filters.raw_query:
            qs = filters.raw_query
        elif filters and filters.field == "title":
            qs = f"TITLE({query})"
        elif filters and filters.field == "abstract":
            qs = f"ABS({query})"
        else:
            qs = query

        body: dict = {
            "qs": qs,
            "display": {"show": min(max_results, 100), "offset": 0, "sortBy": "relevance"},
        }
        if self._oa_only:
            body["filters"] = {"openAccess": True}
        if filters:
            # The ``authors`` field is a single search string; joining several
            # names would require all of them.  Several authors (meaning
            # "any of") are left to the framework's post-filter.
            if len(filters.authors) == 1:
                body["authors"] = filters.authors[0]
            if filters.journal:
                body["pub"] = filters.journal
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to = filters.year_to or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                body["date"] = f"{y_from or y_to}-{y_to or y_from}"

        resp = with_retry(lambda: httpx.put(_SEARCH, json=body, headers=headers, timeout=30))
        resp.raise_for_status()
        data = resp.json()
        return [self._parse(item) for item in data.get("results", [])]

    def _parse(self, item: dict) -> Paper:
        """Parse a single ScienceDirect result dict into a Paper.

        Args:
            item: A dict from the ScienceDirect ``results`` array, containing
                fields such as ``title``, ``authors``, ``doi``, ``pii``,
                ``publicationDate``, ``sourceTitle``, ``openAccess``, and
                ``uri``.

        Returns:
            A Paper populated with available bibliographic metadata.
            ``pdf_url`` is left unset: the Elsevier article endpoint needs the
            ``X-ELS-APIKey`` header, which the generic downloader does not
            send, so exposing it would only produce failed (or bogus)
            downloads.  Open-access articles are still fetched through the
            downloader's Unpaywall / browser-session fallbacks, or via
            ``download_pdf``.
        """
        pages = item.get("pages") or {}
        first = pages.get("first", "")
        last = pages.get("last", "")
        page_str = f"{first}-{last}" if first and last else first or None

        authors = [a.get("name") for a in item.get("authors") or [] if a.get("name")]

        year = parse_year(item.get("publicationDate"))

        volume, issue = _split_volume_issue(item.get("volumeIssue"))

        return Paper(
            title=item.get("title") or "",
            authors=authors,
            year=year,
            doi=normalise_doi(item.get("doi")),
            pii=item.get("pii"),
            journal=item.get("sourceTitle"),
            volume=volume,
            issue=issue,
            pages=page_str,
            pdf_url=None,
            source=self.name,
            is_open_access=item.get("openAccess", False),
            url=item.get("uri"),
        )

    def download_pdf(self, doi: str, dest: str) -> None:
        """Download the PDF for an open-access article by DOI.

        Streams the PDF from the Elsevier article endpoint and writes it to
        the local filesystem.

        Args:
            doi: The article DOI (used to construct the Elsevier article URL).
            dest: Absolute or relative path to the destination file.
        """
        headers = {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/pdf",
        }
        if self._inst_token:
            headers["X-ELS-Insttoken"] = self._inst_token

        with httpx.stream(
            "GET", _ARTICLE.format(doi=doi), headers=headers, timeout=60, follow_redirects=True
        ) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(8192):
                    f.write(chunk)
