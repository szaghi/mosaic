"""CrossRef citation provider — secondary/fallback implementation.

CrossRef reference deposit is inconsistent across publishers: many journals
do not deposit reference lists, so coverage varies significantly.  Use this
provider as a supplement to OpenAlex, not as a primary source.

API: GET https://api.crossref.org/works/{doi}
Response field: message.reference[].DOI
No auth required; use the polite pool via User-Agent mailto header.
"""

from __future__ import annotations

import logging

import httpx

from mosaic.citations.base import BaseCitationProvider
from mosaic.models import Paper

_log = logging.getLogger(__name__)

_CR_BASE = "https://api.crossref.org/works"


class CrossRefCitationProvider(BaseCitationProvider):
    """Fetch outgoing citations from CrossRef's reference deposit.

    Only papers with a DOI are supported.  CrossRef returns a ``reference``
    list under ``message``; each entry may contain a ``DOI`` field.  Entries
    without a DOI (unstructured references) are silently skipped.
    """

    name = "crossref"

    def __init__(self, email: str = "") -> None:
        self._email = email

    def can_handle(self, paper: Paper) -> bool:
        return bool(paper.doi)

    def fetch_references(self, paper: Paper) -> list[str]:
        if not paper.doi:
            return []
        headers: dict = {}
        if self._email:
            headers["User-Agent"] = f"mosaic/1.0 (mailto:{self._email})"
        try:
            resp = httpx.get(
                f"{_CR_BASE}/{paper.doi}",
                headers=headers,
                params={"select": "reference"},
                timeout=30,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            refs = resp.json().get("message", {}).get("reference") or []
            uids: list[str] = []
            for ref in refs:
                doi = (ref.get("DOI") or "").strip().lower()
                if doi:
                    uids.append(f"doi:{doi}")
            return uids
        except Exception as exc:
            _log.warning("CrossRef: citation fetch failed for %s: %s", paper.uid, exc)
            return []
