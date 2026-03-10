"""Zotero integration — local API (port 23119) and web API (api.zotero.org)."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from mosaic.models import Paper

_LOCAL_BASE = "http://localhost:{port}/api/users/0"
_WEB_BASE   = "https://api.zotero.org/users/{user_id}"
_KEYS_URL   = "https://api.zotero.org/keys/{key}"

# arXiv and preprint-like sources map to "preprint"; everything else to
# "journalArticle" which is Zotero's most common item type.
_PREPRINT_SOURCES = {"arXiv", "bioRxiv", "medRxiv"}


class ZoteroClient:
    """Thin client for the Zotero item API.

    Two modes, selected automatically:
    - **Local** (default): talks to ``http://localhost:{port}/api/users/0``.
      Requires Zotero desktop to be running.  No credentials needed.
    - **Web**: talks to ``https://api.zotero.org/users/{user_id}``.
      Requires *api_key*; *user_id* is auto-discovered on first use if left
      at the default value of 0.
    """

    def __init__(self, *, api_key: str = "", user_id: int = 0, port: int = 23119) -> None:
        self._api_key  = api_key
        self._user_id  = user_id
        self._port     = port

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
                url = _KEYS_URL.format(key=self._api_key)
            else:
                url = f"http://localhost:{self._port}/api/"
            with httpx.Client(timeout=5) as client:
                r = client.get(url, headers=self._headers)
                return 200 <= r.status_code < 300
        except Exception:
            return False

    def discover_user_id(self) -> int:
        """Fetch the user ID from the API key and cache it.

        Only relevant in web mode.  Updates ``self._user_id`` in place and
        returns the value so the caller can persist it to config.
        """
        if not self._web_mode:
            return 0
        with httpx.Client(timeout=10) as client:
            r = client.get(_KEYS_URL.format(key=self._api_key), headers=self._headers)
            r.raise_for_status()
        uid = r.json()["userID"]
        self._user_id = uid
        return uid

    def ensure_collection(self, name: str) -> str:
        """Return the key of *name*, creating the collection if it does not exist."""
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
            r.raise_for_status()
        return list(r.json()["successful"].values())[0]["key"]

    def add_papers(
        self,
        papers: list[Paper],
        collection_key: str | None = None,
    ) -> list[str]:
        """Add *papers* to Zotero.

        Returns a list of the same length as *papers*: each entry is the
        created item key, or an empty string if that item failed.
        """
        items = [_paper_to_item(p, collection_key) for p in papers]
        result = [""] * len(items)
        for start in range(0, len(items), 50):          # Zotero max 50/request
            chunk = items[start : start + 50]
            with httpx.Client(timeout=30) as client:
                r = client.post(f"{self._base}/items", headers=self._headers, json=chunk)
                r.raise_for_status()
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

        payload = [{
            "itemType":    "attachment",
            "parentItem":  item_key,
            "linkMode":    "linked_file",
            "path":        str(pdf_path.resolve()),
            "title":       pdf_path.name,
            "contentType": "application/pdf",
        }]
        try:
            with httpx.Client(timeout=10) as client:
                r = client.post(f"{self._base}/items", headers=self._headers, json=payload)
                r.raise_for_status()
            return bool(r.json().get("successful"))
        except Exception:
            return False


# ── helpers ───────────────────────────────────────────────────────────────────

def _paper_to_item(paper: Paper, collection_key: str | None = None) -> dict:
    """Convert a :class:`~mosaic.models.Paper` to a Zotero item dict."""
    item_type = "preprint" if paper.source in _PREPRINT_SOURCES else "journalArticle"
    item: dict = {
        "itemType": item_type,
        "title":    paper.title or "",
        "creators": [_parse_author(a) for a in (paper.authors or [])],
        "date":     str(paper.year) if paper.year else "",
        "abstractNote": paper.abstract or "",
        "url":      paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else ""),
        "DOI":      paper.doi or "",
    }
    if paper.journal:
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
        return {"creatorType": "author", "firstName": parts[0].strip(), "lastName": parts[1].strip()}
    return {"creatorType": "author", "lastName": name, "firstName": ""}
