"""Generic configurable REST source — driven entirely from a TOML config dict."""
from __future__ import annotations
import re
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource


def _get_nested(obj: dict, path: str):
    """Navigate a dot-notation path in a nested dict. Returns None if missing."""
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _parse_year(val) -> int | None:
    """Extract a 4-digit year from an int, string year, or ISO date string."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    m = re.search(r"\b(\d{4})\b", str(val))
    return int(m.group(1)) if m else None


class CustomSource(BaseSource):
    """A generic REST search source configured entirely from a TOML dict.

    Supported config keys
    ---------------------
    name              str   — display name (required)
    url               str   — API endpoint URL (required)
    method            str   — "GET" (default) or "POST"
    query_param       str   — param/body key for the search query (default "q")
    results_path      str   — dot-notation path to the results array in the
                              JSON response (default "results")
    api_key           str   — optional API key value
    api_key_header    str   — header name for the API key (default "X-API-Key")
    max_results_param str   — optional param/body key for the page size

    [fields]          table — dot-notation paths within each result object:
        title, doi, year, abstract, journal, pdf_url, url, is_open_access

    authors           str   — dot-notation path to a flat string array of authors
    authors_path      str   — dot-notation path to an array of author objects
    authors_field     str   — key within each author object holding the name
                              (used together with authors_path)
    """

    def __init__(self, cfg: dict) -> None:
        self.name             = cfg["name"]
        self._url             = cfg.get("url", "")
        self._method          = cfg.get("method", "GET").upper()
        self._query_param     = cfg.get("query_param", "q")
        self._results_path    = cfg.get("results_path", "results")
        self._api_key         = cfg.get("api_key", "")
        self._api_key_header  = cfg.get("api_key_header", "X-API-Key")
        self._max_results_param = cfg.get("max_results_param", "")
        self._fields: dict    = cfg.get("fields", {})
        self._authors_path    = cfg.get("authors_path", "")
        self._authors_field   = cfg.get("authors_field", "")

    def available(self) -> bool:
        return bool(self._url)

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        q = filters.raw_query if (filters and filters.raw_query) else query

        headers: dict = {"Accept": "application/json"}
        if self._api_key and self._api_key_header:
            headers[self._api_key_header] = self._api_key

        limit = min(max_results, 100)

        if self._method == "GET":
            params: dict = {self._query_param: q}
            if self._max_results_param:
                params[self._max_results_param] = limit
            resp = httpx.get(self._url, params=params, headers=headers, timeout=30)
        else:
            body: dict = {self._query_param: q}
            if self._max_results_param:
                body[self._max_results_param] = limit
            resp = httpx.post(self._url, json=body, headers=headers, timeout=30)

        resp.raise_for_status()
        data = resp.json()

        results = _get_nested(data, self._results_path) if self._results_path else data
        if not isinstance(results, list):
            return []

        return [self._parse(item) for item in results[:max_results]]

    def _parse(self, item: dict) -> Paper:
        def field(key: str):
            path = self._fields.get(key, "")
            return _get_nested(item, path) if path else None

        if self._authors_path and self._authors_field:
            raw = _get_nested(item, self._authors_path) or []
            authors = [
                a.get(self._authors_field, "")
                for a in raw
                if isinstance(a, dict)
            ]
        elif "authors" in self._fields:
            raw = _get_nested(item, self._fields["authors"]) or []
            authors = [str(a) for a in raw if a]
        else:
            authors = []

        return Paper(
            title=str(field("title") or ""),
            authors=authors,
            year=_parse_year(field("year")),
            doi=field("doi") or None,
            abstract=field("abstract") or None,
            journal=field("journal") or None,
            pdf_url=field("pdf_url") or None,
            url=field("url") or None,
            source=self.name,
            is_open_access=bool(field("is_open_access")),
        )
