"""Unpaywall — resolve OA PDF URLs for any DOI."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import httpx

_BASE = "https://api.unpaywall.org/v2/{doi}"

# Publisher-hosted OA PDFs are often behind bot walls (Akamai, Radware) that
# refuse any scripted client, while the same paper's repository copy downloads
# fine. Trying every location, not just "best", is what makes these succeed.
MAX_CANDIDATES = 6

# HAL record landing pages, e.g. https://hal.science/hal-02877468 (optionally
# with a version suffix); the PDF is served at <landing>/document.
_HAL_HOSTS = ("hal.science", "archives-ouvertes.fr")
_HAL_ID = re.compile(r"^/[a-z0-9]+-\d{8}(v\d+)?/?$")


def _hal_document(url: str) -> str | None:
    """Return the PDF URL for a HAL landing page, or None if *url* is not one."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in _HAL_HOSTS):
        return None
    if not _HAL_ID.match(parts.path):
        return None
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}/document"


def candidates(doi: str, email: str) -> list[str]:
    """Return candidate OA PDF URLs for *doi*, most promising first.

    Order: every location's ``url_for_pdf`` (best location first, then the
    rest in Unpaywall's order), then HAL ``/document`` URLs derived from HAL
    landing pages, then the best location's landing ``url`` as a last resort.
    Callers must still verify each response is a PDF.
    """
    if not doi or not email:
        return []
    try:
        resp = httpx.get(_BASE.format(doi=doi), params={"email": email}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    if not data.get("is_oa"):
        return []

    best = data.get("best_oa_location") or {}
    locations = [best, *(data.get("oa_locations") or [])]
    urls = [loc.get("url_for_pdf") for loc in locations]
    urls += [_hal_document(loc.get("url") or "") for loc in locations]
    urls.append(best.get("url"))
    return list(dict.fromkeys(u for u in urls if u))[:MAX_CANDIDATES]


def resolve(doi: str, email: str) -> str | None:
    """Return the best OA PDF URL for a DOI, or None if not found."""
    found = candidates(doi, email)
    return found[0] if found else None
