"""OpenAlex citation provider — primary implementation."""

from __future__ import annotations

import logging
import time

import httpx

from mosaic.citations.base import BaseCitationProvider
from mosaic.models import Paper

_log = logging.getLogger(__name__)

_OA_BASE = "https://api.openalex.org"
_BATCH_SIZE = 50          # W-IDs per /works batch call
_BATCH_DELAY = 1.0        # seconds between batch calls (polite pool)


class OpenAlexCitationProvider(BaseCitationProvider):
    """Fetch outgoing citations via the OpenAlex works API.

    Strategy:
      1. Resolve *paper* to an OpenAlex work URL using ``openalex_id`` (when
         already stored), DOI, or arXiv ID.
      2. Fetch ``referenced_works`` — a list of W-ID URLs.
      3. Batch-resolve W-IDs to DOIs (≤ 50 per call) and normalise to
         mosaic UIDs.

    All API calls are made to the polite pool when an email is configured
    (``cfg["unpaywall"]["email"]`` or ``cfg["sources"]["openalex"]["email"]``).
    """

    name = "openalex"

    def __init__(self, email: str = "") -> None:
        self._email = email

    def can_handle(self, paper: Paper) -> bool:
        return bool(paper.doi or paper.arxiv_id or paper.openalex_id)

    def fetch_references(self, paper: Paper) -> list[str]:
        w_ids = self._get_referenced_w_ids(paper)
        if not w_ids:
            return []
        return self._resolve_w_ids(w_ids)

    # ── private helpers ───────────────────────────────────────────────────────

    def _get_referenced_w_ids(self, paper: Paper) -> list[str]:
        url = self._work_url(paper)
        if not url:
            return []
        params: dict = {"select": "id,referenced_works"}
        if self._email:
            params["mailto"] = self._email
        try:
            resp = httpx.get(url, params=params, timeout=30)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            related = data.get("referenced_works") or []
            # "https://openalex.org/W2963403868" → "W2963403868"
            return [r.rsplit("/", 1)[-1] for r in related if r]
        except Exception as exc:
            _log.warning("OpenAlex: failed to fetch referenced_works for %s: %s", paper.uid, exc)
            return []

    def _resolve_w_ids(self, w_ids: list[str]) -> list[str]:
        """Batch-resolve OpenAlex W-IDs to mosaic UIDs."""
        uids: list[str] = []
        for i in range(0, len(w_ids), _BATCH_SIZE):
            batch = w_ids[i : i + _BATCH_SIZE]
            params: dict = {
                "filter": f"ids.openalex:{'|'.join(batch)}",
                "per_page": len(batch),
                "select": "id,doi,ids",
            }
            if self._email:
                params["mailto"] = self._email
            try:
                resp = httpx.get(f"{_OA_BASE}/works", params=params, timeout=30)
                resp.raise_for_status()
                for item in resp.json().get("results", []):
                    uid = _item_to_uid(item)
                    if uid:
                        uids.append(uid)
            except Exception as exc:
                _log.warning("OpenAlex: W-ID batch resolution failed: %s", exc)
            if i + _BATCH_SIZE < len(w_ids):
                time.sleep(_BATCH_DELAY)
        return uids

    def _work_url(self, paper: Paper) -> str | None:
        if paper.openalex_id:
            return f"{_OA_BASE}/works/{paper.openalex_id}"
        if paper.doi:
            return f"{_OA_BASE}/works/https://doi.org/{paper.doi}"
        if paper.arxiv_id:
            return f"{_OA_BASE}/works/https://arxiv.org/abs/{paper.arxiv_id}"
        return None


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _item_to_uid(item: dict) -> str | None:
    """Convert an OpenAlex work dict to a mosaic UID.

    Mirrors the logic in ``Paper.uid`` so that resolved UIDs match those
    stored in the local papers table.

    Args:
        item: A partial OpenAlex work dict containing ``doi`` and/or ``ids``.

    Returns:
        A mosaic UID string, or ``None`` if no usable identifier is found.
    """
    doi_raw = (item.get("doi") or "").removeprefix("https://doi.org/").strip()
    if doi_raw:
        doi_lower = doi_raw.lower()
        if doi_lower.startswith("10.48550/arxiv."):
            return f"arxiv:{doi_lower.removeprefix('10.48550/arxiv.')}"
        return f"doi:{doi_lower}"
    ids = item.get("ids") or {}
    arxiv_raw = (ids.get("arxiv") or "").removeprefix("https://arxiv.org/abs/").strip()
    if arxiv_raw:
        return f"arxiv:{arxiv_raw}"
    return None
