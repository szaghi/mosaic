"""Shared orchestration logic used by both the CLI and the web UI.

Functions here encapsulate the *business* side of multi-step operations
(Zotero export, Obsidian export, batch PDF download) so that the CLI and
UI are thin presentation wrappers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mosaic.db import Cache
from mosaic.downloader import download as dl_paper
from mosaic.models import Paper

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF batch download
# ---------------------------------------------------------------------------


def download_papers(
    papers: list[Paper],
    cfg: dict,
    cache: Cache,
) -> dict[str, str]:
    """Download PDFs for *papers*.

    Returns:
        A ``{paper.uid: local_path}`` mapping for successful downloads.
    """
    email = cfg.get("unpaywall", {}).get("email", "")
    download_dir = cfg["download_dir"]
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")
    pdf_map: dict[str, str] = {}
    for p in papers:
        if not (p.pdf_url or p.doi):
            continue
        path = dl_paper(p, download_dir, cache, email, pattern)
        if path:
            pdf_map[p.uid] = path
    return pdf_map


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

    item_keys = client.add_papers(papers, collection_key=collection_key)
    added = sum(1 for k in item_keys if k)

    attached = 0
    if pdf_map:
        for paper, item_key in zip(papers, item_keys, strict=False):
            if not item_key:
                continue
            local_path = pdf_map.get(paper.uid)
            if (
                local_path
                and Path(local_path).exists()
                and client.attach_pdf(item_key, Path(local_path))
            ):
                attached += 1

    label = f" to '{collection_name}'" if collection_name else ""
    return {
        "ok": True,
        "msg": f"{added} paper(s) added to Zotero{label}.",
        "added": added,
        "attached": attached,
    }


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
    added, skipped = vault.export_papers(papers)
    msg = f"{added} note(s) added"
    if skipped:
        msg += f", {skipped} skipped (already exist)"
    msg += f" → {vault.notes_dir}"
    return {"ok": True, "msg": msg}
