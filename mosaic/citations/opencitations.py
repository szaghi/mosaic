"""OpenCitations (COCI) citation provider — tertiary/supplementary implementation.

OpenCitations indexes open citation data derived from open-access literature.
Coverage skews toward OA journals and may be sparse for paywalled content.
Use as a supplementary source when OpenAlex and CrossRef both return nothing.

API: GET https://opencitations.net/index/coci/api/v1/references/{doi}
Response: list of objects with a ``cited`` field containing ``"doi:10.xxx/yyy"``.
No auth required.
"""

from __future__ import annotations

import logging

import httpx

from mosaic.citations.base import BaseCitationProvider
from mosaic.models import Paper

_log = logging.getLogger(__name__)

_OC_BASE = "https://opencitations.net/index/coci/api/v1"


class OpenCitationsCitationProvider(BaseCitationProvider):
    """Fetch outgoing citations from the OpenCitations COCI index.

    Only papers with a DOI are supported.  The COCI API returns a list of
    objects; the ``cited`` field contains a DOI prefixed with ``"doi:"``.
    """

    name = "opencitations"

    def can_handle(self, paper: Paper) -> bool:
        return bool(paper.doi)

    def fetch_references(self, paper: Paper) -> list[str]:
        if not paper.doi:
            return []
        try:
            resp = httpx.get(
                f"{_OC_BASE}/references/{paper.doi}",
                timeout=30,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            uids: list[str] = []
            for item in resp.json():
                cited = (item.get("cited") or "").strip()
                # Field is typically "doi:10.xxx/yyy" — normalise to mosaic format
                if cited.lower().startswith("doi:"):
                    cited = cited[4:]
                if cited:
                    uids.append(f"doi:{cited.lower()}")
            return uids
        except Exception as exc:
            _log.warning("OpenCitations: citation fetch failed for %s: %s", paper.uid, exc)
            return []
