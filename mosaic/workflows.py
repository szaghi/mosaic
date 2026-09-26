"""Shared orchestration logic used by both the CLI and the web UI.

Functions here encapsulate the *business* side of multi-step operations
(Zotero export, Obsidian export, batch PDF download) so that the CLI and
UI are thin presentation wrappers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mosaic.db import Cache
from mosaic.downloader import download as dl_paper
from mosaic.models import Paper

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF batch download
# ---------------------------------------------------------------------------


@dataclass
class DownloadItem:
    paper: Paper
    status: str  # "ok" | "fail" | "skip"
    path: str | None = None


@dataclass
class DownloadReport:
    items: list[DownloadItem] = field(default_factory=list)

    @property
    def pdf_map(self) -> dict[str, str]:
        """``{paper.uid: local_path}`` for successful downloads."""
        return {i.paper.uid: i.path for i in self.items if i.status == "ok" and i.path}

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)


def download_papers(
    papers: list[Paper],
    cfg: dict,
    cache: Cache,
    *,
    skip_without_link: bool = True,
    on_start: Callable[[Paper], None] | None = None,
    on_item: Callable[[DownloadItem], None] | None = None,
) -> DownloadReport:
    """Download PDFs for *papers*, reporting each outcome.

    Args:
        skip_without_link: Skip papers with neither ``pdf_url`` nor DOI
            (status ``"skip"``) instead of attempting them.
        on_start: Called before each download attempt (progress display).
        on_item: Called with each :class:`DownloadItem` as soon as it is known.
    """
    email = cfg.get("unpaywall", {}).get("email", "")
    download_dir = cfg["download_dir"]
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")
    report = DownloadReport()
    for p in papers:
        if skip_without_link and not (p.pdf_url or p.doi):
            item = DownloadItem(p, "skip")
        else:
            if on_start:
                on_start(p)
            path = dl_paper(p, download_dir, cache, email, pattern)
            item = DownloadItem(p, "ok" if path else "fail", str(path) if path else None)
        report.items.append(item)
        if on_item:
            on_item(item)
    return report


def bulk_get(
    dois: list[str],
    cfg: dict,
    cache: Cache,
    *,
    on_start: Callable[[Paper], None] | None = None,
    on_item: Callable[[DownloadItem], None] | None = None,
) -> tuple[list[Paper], DownloadReport]:
    """Download one PDF per DOI, reusing cached metadata when the DOI is known.

    Returns ``(papers, report)``; *papers* are the cached records (or bare
    stubs) in DOI order, ready for Zotero/Obsidian export or indexing.
    """
    from mosaic.services import papers_for_dois

    papers = papers_for_dois(cache, dois)
    report = download_papers(
        papers, cfg, cache, skip_without_link=False, on_start=on_start, on_item=on_item
    )
    return papers, report


# ---------------------------------------------------------------------------
# Search results
# ---------------------------------------------------------------------------


def finalize_search(
    papers: list[Paper],
    cfg: dict,
    cache: Cache,
    *,
    query: str,
    oa_only: bool = False,
    pdf_only: bool = False,
    sort_by: str = "",
    prefer_cache: bool = False,
    save: bool = True,
    history: dict | None = None,
) -> list[Paper]:
    """Shared tail of every search: cache preference, filters, sorting, persistence.

    Args:
        prefer_cache: Replace known papers with their (richer) cached record
            *before* filtering, so e.g. a cached ``pdf_url`` counts for ``pdf_only``.
        save: Upsert the resulting papers into the cache.
        history: When given, log the search (``{"filters": {...}, "sources": [...]}``)
            so it shows up in the web UI history.

    Raises:
        ValueError: for an unknown *sort_by* value.
    """
    import json

    from mosaic.services import post_process

    if prefer_cache:
        rich = cache.rich_uids()
        papers = [(cache.get_by_uid(p.uid) or p) if p.uid in rich else p for p in papers]
    papers = post_process(
        papers, query=query, cfg=cfg, oa_only=oa_only, pdf_only=pdf_only, sort_by=sort_by
    )
    if save:
        for p in papers:
            cache.save(p)
    if history is not None:
        cache.save_search(
            query=query,
            filters_json=json.dumps(history.get("filters", {})),
            sources_json=json.dumps(history.get("sources", [])),
            result_count=len(papers),
        )
    return papers


# ---------------------------------------------------------------------------
# RAG auto-index
# ---------------------------------------------------------------------------


def auto_index(papers: list[Paper], cfg: dict, cache: Cache) -> str | None:
    """Index *papers* when ``rag.auto_index`` is enabled.

    Never raises: returns a warning message on failure (``None`` otherwise) so
    that a broken embedding setup is reported instead of silently ignored.
    """
    if not papers or not cfg.get("rag", {}).get("auto_index"):
        return None
    try:
        from mosaic.rag import index_papers

        index_papers(papers, cfg, cache, progress=False)
    except Exception as e:
        log.debug("Auto-index failed", exc_info=True)
        return f"Auto-index failed: {e}"
    return None


# ---------------------------------------------------------------------------
# Zotero export
# ---------------------------------------------------------------------------


def push_to_zotero(
    papers: list[Paper],
    cfg: dict,
    *,
    collection_name: str = "",
    force_local: bool = False,
    pdf_map: dict[str, str] | None = None,
) -> dict:
    """Export *papers* to Zotero (local or web API).

    Returns:
        A result dict ``{"ok": bool, "msg": str, "added": int, "attached": int}``.
    """
    from mosaic.zotero import ZoteroClient

    zot_cfg = cfg.get("zotero", {})
    api_key = "" if force_local else zot_cfg.get("api_key", "")
    user_id = zot_cfg.get("user_id", 0)
    client = ZoteroClient(api_key=api_key, user_id=user_id)

    if api_key and not user_id:
        # Key saved without its user ID (e.g. set from the web UI or by hand):
        # every web API call would otherwise target /users/0.
        try:
            zot_cfg["user_id"] = client.discover_user_id()
        except Exception as e:
            return {
                "ok": False,
                "msg": f"Could not determine the Zotero user ID for this API key: {e}",
            }

    if not client.is_reachable():
        if api_key:
            return {"ok": False, "msg": "Zotero web API not reachable. Check your API key."}
        return {
            "ok": False,
            "msg": "No Zotero API key configured and Zotero desktop is not running. "
            "Either set a Zotero web API key in Config, or start the Zotero desktop app.",
        }

    collection_key: str | None = None
    if collection_name:
        try:
            collection_key = client.ensure_collection(collection_name)
        except Exception as e:
            return {
                "ok": False,
                "msg": f"Could not create/find collection '{collection_name}': {e}",
            }

    try:
        item_keys = client.add_papers(papers, collection_key=collection_key)
    except Exception as e:
        return {"ok": False, "msg": f"Zotero rejected the new items: {e}"}
    added = sum(1 for k in item_keys if k)

    attached = 0
    if pdf_map:
        for paper, item_key in zip(papers, item_keys, strict=False):
            if not item_key:
                continue
            local_path = pdf_map.get(paper.uid)
            try:
                if (
                    local_path
                    and Path(local_path).exists()
                    and client.attach_pdf(item_key, Path(local_path))
                ):
                    attached += 1
            except Exception:
                log.warning("Could not attach %s to Zotero item %s", local_path, item_key)

    label = f" to '{collection_name}'" if collection_name else ""
    return {
        "ok": True,
        "msg": f"{added} paper(s) added to Zotero{label}.",
        "added": added,
        "attached": attached,
    }


def configure_zotero_key(cfg: dict, api_key: str) -> str | None:
    """Store a Zotero web API key in *cfg* and discover its user ID.

    Returns a warning message when the user ID could not be discovered (it
    will be retried on the first export), ``None`` on success.
    """
    from mosaic.zotero import ZoteroClient

    zot_cfg = cfg.setdefault("zotero", {})
    if zot_cfg.get("api_key") != api_key:
        zot_cfg["user_id"] = 0
    zot_cfg["api_key"] = api_key
    try:
        zot_cfg["user_id"] = ZoteroClient(api_key=api_key).discover_user_id()
    except Exception as e:
        return f"Could not auto-discover Zotero user ID: {e}"
    return None


# ---------------------------------------------------------------------------
# Obsidian export
# ---------------------------------------------------------------------------


def push_to_obsidian(
    papers: list[Paper],
    cfg: dict,
    *,
    subfolder_override: str = "",
) -> dict:
    """Export *papers* as Obsidian notes.

    Returns:
        A result dict ``{"ok": bool, "msg": str}``.
    """
    from mosaic.obsidian import ObsidianVault

    obs_cfg = cfg.get("obsidian", {})
    vault_path = obs_cfg.get("vault_path", "")
    if not vault_path:
        return {"ok": False, "msg": "Obsidian vault path is not configured."}

    vault = ObsidianVault(
        vault_path=vault_path,
        subfolder=subfolder_override or obs_cfg.get("subfolder", "papers"),
        filename_pattern=obs_cfg.get("filename_pattern", "{year}_{author}_{title}"),
        tags=obs_cfg.get("tags", ["paper"]),
        wikilinks=obs_cfg.get("wikilinks", True),
    )
    try:
        added, skipped = vault.export_papers(papers)
    except OSError as e:
        return {"ok": False, "msg": f"Could not write Obsidian notes: {e}"}
    msg = f"{added} note(s) added"
    if skipped:
        msg += f", {skipped} skipped (already exist)"
    msg += f" → {vault.notes_dir}"
    return {"ok": True, "msg": msg}
