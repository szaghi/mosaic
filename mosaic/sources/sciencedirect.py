"""Elsevier ScienceDirect API (open access only by default)."""
from __future__ import annotations
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_SEARCH = "https://api.elsevier.com/content/search/sciencedirect"
_ARTICLE = "https://api.elsevier.com/content/article/doi/{doi}"


class ScienceDirectSource(BaseSource):
    name = "ScienceDirect"

    def __init__(self, api_key: str = "", inst_token: str = "", open_access_only: bool = True):
        self._api_key = api_key
        self._inst_token = inst_token
        self._oa_only = open_access_only

    def available(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        headers = {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/json",
        }
        if self._inst_token:
            headers["X-ELS-Insttoken"] = self._inst_token

        body: dict = {
            "qs": query,
            "display": {"show": min(max_results, 100), "offset": 0, "sortBy": "relevance"},
        }
        if self._oa_only:
            body["filters"] = {"openAccess": True}
        if filters:
            if filters.authors:
                body["authors"] = " ".join(filters.authors)
            if filters.journal:
                body["pub"] = filters.journal
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                body["date"] = f"{y_from or y_to}-{y_to or y_from}"

        resp = httpx.put(_SEARCH, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return [self._parse(item) for item in data.get("results", [])]

    def _parse(self, item: dict) -> Paper:
        pages = item.get("pages") or {}
        first = pages.get("first", "")
        last = pages.get("last", "")
        page_str = f"{first}-{last}" if first and last else first or None

        authors = [a.get("name", "") for a in item.get("authors", [])]

        pub_date = item.get("publicationDate") or ""
        year = int(pub_date[:4]) if pub_date else None

        doi = item.get("doi")
        pdf_url = None
        if doi and item.get("openAccess"):
            pdf_url = _ARTICLE.format(doi=doi)  # requires Accept: application/pdf when downloading

        return Paper(
            title=item.get("title") or "",
            authors=authors,
            year=year,
            doi=doi,
            pii=item.get("pii"),
            journal=item.get("sourceTitle"),
            volume=item.get("volumeIssue"),
            pages=page_str,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=item.get("openAccess", False),
            url=item.get("uri"),
        )

    def download_pdf(self, doi: str, dest: str) -> None:
        """Download PDF for an OA article by DOI."""
        headers = {
            "X-ELS-APIKey": self._api_key,
            "Accept": "application/pdf",
        }
        if self._inst_token:
            headers["X-ELS-Insttoken"] = self._inst_token

        with httpx.stream("GET", _ARTICLE.format(doi=doi), headers=headers, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(8192):
                    f.write(chunk)
