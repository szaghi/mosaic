"""Unpaywall — resolve OA PDF URL for any DOI."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from mosaic.parsing import normalise_doi

_BASE = "https://api.unpaywall.org/v2/{doi}"


def resolve(doi: str, email: str) -> str | None:
    """Return the best OA PDF URL for a DOI, or None if not found."""
    doi = normalise_doi(doi) or ""
    if not doi or not email:
        return None
    try:
        # DOIs may contain "#", "?" or "%", which would corrupt the path; the
        # "/" separating prefix and suffix is kept as Unpaywall expects it.
        resp = httpx.get(
            _BASE.format(doi=quote(doi, safe="/")), params={"email": email}, timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("is_oa"):
            return None
        best = data.get("best_oa_location") or {}
        return best.get("url_for_pdf") or best.get("url")
    except Exception:
        return None
