"""Zotero integration — local API (port 23119) and web API (api.zotero.org)."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from mosaic.models import Paper

log = logging.getLogger(__name__)

_LOCAL_BASE = "http://localhost:{port}/api/users/0"
_WEB_BASE = "https://api.zotero.org/users/{user_id}"
# The key travels in the Zotero-API-Key header, never in the URL: URLs end up
# in exception messages and logs.
_KEYS_URL = "https://api.zotero.org/keys/current"

# arXiv and preprint-like sources map to "preprint"; everything else to
# "journalArticle" which is Zotero's most common item type.
_PREPRINT_SOURCES = {"arXiv", "bioRxiv", "medRxiv", "bioRxiv/medRxiv"}

# Local API status codes that mean "writes are not available here" (read-only
# local API, endpoint missing, or not authorised) rather than a transient error.
_LOCAL_WRITE_REFUSED = {401, 403, 404, 405, 501}


class ZoteroClient:
    """Thin client for the Zotero item API.

    Two modes, selected automatically:
    - **Local** (default): talks to ``http://localhost:{port}/api/users/0``.
      Requires Zotero desktop to be running.  No credentials needed.
    - **Web**: talks to ``https://api.zotero.org/users/{user_id}``.
      Requires *api_key*; *user_id* is auto-discovered on the first write if
      left at the default value of 0 (read :attr:`user_id` to persist it).
    """

    def __init__(self, *, api_key: str = "", user_id: int = 0, port: int = 23119) -> None:
        self._api_key = api_key
        self._user_id = user_id
        self._port = port

    # ── mode helpers ──────────────────────────────────────────────────────────

    @property
    def _web_mode(self) -> bool:
        return bool(self._api_key)

    @property
    def _base(self) -> str:
        if self._web_mode:
            return _WEB_BASE.format(user_id=self._user_id)
        return _LOCAL_BASE.format(port=self._port)

    @property
    def user_id(self) -> int:
        """The Zotero user ID in use (0 until discovered in web mode)."""
        return self._user_id

    @property
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._web_mode:
            h["Zotero-API-Key"] = self._api_key
        return h

    # ── public API ────────────────────────────────────────────────────────────

    def is_reachable(self) -> bool:
        """Return True if the Zotero API responds (local or web)."""
        try:
            if self._web_mode:
                url = _KEYS_URL
            else:
                url = f"http://localhost:{self._port}/api/"
            with httpx.Client(timeout=5) as client:
                r = client.get(url, headers=self._headers)
                return 200 <= r.status_code < 300
        except Exception:
            log.debug("Zotero reachability check failed", exc_info=True)
            return False

    def discover_user_id(self) -> int:
        """Fetch the user ID from the API key and cache it.

        Only relevant in web mode.  Updates ``self._user_id`` in place and
        returns the value so the caller can persist it to config.
        """
        if not self._web_mode:
            return 0
        with httpx.Client(timeout=10) as client:
            r = client.get(_KEYS_URL, headers=self._headers)
            r.raise_for_status()
        uid = r.json()["userID"]
        self._user_id = uid
        return uid

    def _ensure_user_id(self) -> None:
        """Discover the user ID before the first web-mode request that needs it."""
        if self._web_mode and not self._user_id:
            self.discover_user_id()

    def _check_write(self, r: httpx.Response) -> None:
        """Raise for a failed write, with an actionable message in local mode.

        Raises:
            RuntimeError: When the local API refuses writes.
            httpx.HTTPStatusError: For any other HTTP error.
        """
        if not self._web_mode and r.status_code in _LOCAL_WRITE_REFUSED:
            raise RuntimeError(
                f"Zotero's local API rejected the write (HTTP {r.status_code}). "
                "The local API may be read-only in your Zotero version — configure a "
                "Zotero web API key with `mosaic config --zotero-key <key>` (or on the "
                "web UI Config page) to export through api.zotero.org instead."
            )
        r.raise_for_status()

    def ensure_collection(self, name: str) -> str:
        """Return the key of *name*, creating the collection if it does not exist.

        Raises:
            RuntimeError: When the local API refuses writes.
            httpx.HTTPError: On other network or HTTP errors.
        """
        self._ensure_user_id()
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{self._base}/collections", headers=self._headers)
            r.raise_for_status()
        for coll in r.json():
            if coll.get("data", {}).get("name") == name:
                return coll["data"]["key"]
        # not found — create
        with httpx.Client(timeout=10) as client:
            r = client.post(
                f"{self._base}/collections",
                headers=self._headers,
                json=[{"name": name, "parentCollection": False}],
            )
            self._check_write(r)
        return next(iter(r.json()["successful"].values()))["key"]

    def add_papers(
        self,
        papers: list[Paper],
        collection_key: str | None = None,
    ) -> list[str]:
        """Add *papers* to Zotero.

        Returns a list of the same length as *papers*: each entry is the
        created item key, or an empty string if that item failed.

        Raises:
            RuntimeError: When the local API refuses writes.
            httpx.HTTPError: On other network or HTTP errors.
        """
        self._ensure_user_id()
        items = [_paper_to_item(p, collection_key) for p in papers]
        result = [""] * len(items)
        for start in range(0, len(items), 50):  # Zotero max 50/request
            chunk = items[start : start + 50]
            with httpx.Client(timeout=30) as client:
                r = client.post(f"{self._base}/items", headers=self._headers, json=chunk)
                self._check_write(r)
            data = r.json()
            for str_idx, item_data in data.get("successful", {}).items():
                result[start + int(str_idx)] = item_data["key"]
        return result

    def attach_pdf(self, item_key: str, pdf_path: Path) -> bool:
        """Link a local PDF file to an existing Zotero item.

        Local mode: creates a ``linked_file`` child attachment — no bytes are
        copied; Zotero stores an absolute path.

        Web mode: returns False (full upload not implemented in v1).
        """
        if self._web_mode:
            return False

        payload = [
            {
                "itemType": "attachment",
                "parentItem": item_key,
                "linkMode": "linked_file",
                "path": str(pdf_path.resolve()),
                "title": pdf_path.name,
                "contentType": "application/pdf",
            }
        ]
        try:
            with httpx.Client(timeout=10) as client:
                r = client.post(f"{self._base}/items", headers=self._headers, json=payload)
                r.raise_for_status()
            return bool(r.json().get("successful"))
        except Exception:
            log.debug(
                "Failed to attach PDF %s to Zotero item %s", pdf_path, item_key, exc_info=True
            )
            return False


# ── helpers ───────────────────────────────────────────────────────────────────


def _paper_to_item(paper: Paper, collection_key: str | None = None) -> dict:
    """Convert a :class:`~mosaic.models.Paper` to a Zotero item dict."""
    is_preprint = paper.source in _PREPRINT_SOURCES
    item: dict = {
        "itemType": "preprint" if is_preprint else "journalArticle",
        "title": paper.title or "",
        "creators": [_parse_author(a) for a in (paper.authors or [])],
        "date": str(paper.year) if paper.year else "",
        "abstractNote": paper.abstract or "",
        "url": paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else ""),
        "DOI": paper.doi or "",
    }
    if is_preprint:
        # "preprint" items have no publicationTitle field (the API rejects
        # unknown fields): record the server, and any journal reference in Extra.
        item["repository"] = paper.source
        if paper.arxiv_id:
            item["archiveID"] = f"arXiv:{paper.arxiv_id}"
        if paper.journal:
            item["extra"] = f"Published in: {paper.journal}"
    elif paper.journal:
        item["publicationTitle"] = paper.journal
    if collection_key:
        item["collections"] = [collection_key]
    return item


def _parse_author(name: str) -> dict:
    """Parse an author name string into a Zotero creator dict.

    Handles:
    - ``"Last, First"``   — comma-separated
    - ``"First Last"``    — space-separated (last token = lastName)
    - single token        — treated as lastName
    """
    name = name.strip()
    if not name:
        return {"creatorType": "author", "lastName": "", "firstName": ""}
    if "," in name:
        last, _, first = name.partition(",")
        return {"creatorType": "author", "lastName": last.strip(), "firstName": first.strip()}
    parts = name.rsplit(" ", 1)
    if len(parts) == 2:
        return {
            "creatorType": "author",
            "firstName": parts[0].strip(),
            "lastName": parts[1].strip(),
        }
    return {"creatorType": "author", "lastName": name, "firstName": ""}
