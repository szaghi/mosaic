"""Configuration page."""

from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for
from markupsafe import escape

from mosaic.source_registry import SHORTHAND_TO_CFG_KEY
from mosaic.ui.routes.common import app_cfg, app_version, bp

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Secret form fields that are never echoed back into the HTML: an empty field
# keeps the stored value, the matching ``clear_<name>`` checkbox removes it.
_SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "zotero_key": ("zotero", "api_key"),
    "llm_api_key": ("llm", "api_key"),
    "rag_embedding_api_key": ("rag", "embedding_api_key"),
}


def _get_path(cfg: dict, path: tuple[str, ...]):
    node = cfg
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _set_path(cfg: dict, path: tuple[str, ...], value) -> None:
    node = cfg
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _secret_status(cfg: dict) -> dict[str, bool]:
    """Which secret fields currently hold a value (rendered as "set")."""
    from mosaic.config import API_KEY_PATHS

    paths = dict(API_KEY_PATHS) | _SECRET_FIELDS
    return {name: bool(_get_path(cfg, path)) for name, path in paths.items()}


def _form_number(name: str, cast, warnings: list[str], *, lo=None, hi=None):
    """Parse a numeric form field; append a warning and return None when invalid."""
    raw = request.form.get(name, "").strip()
    if not raw:
        return None
    try:
        value = cast(raw)
    except ValueError:
        warnings.append(f"{name}: {raw!r} is not a valid number — not saved.")
        return None
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        bounds = f"between {lo} and {hi}" if hi is not None else f"at least {lo}"
        warnings.append(f"{name}: must be {bounds} — not saved.")
        return None
    return value


@bp.route("/config")
def config_page():
    import mosaic.config as cfg_mod

    cfg = cfg_mod.load()
    return render_template(
        "config.html", cfg=cfg, secrets=_secret_status(cfg), version=app_version()
    )


@bp.route("/config", methods=["POST"])
def config_save():
    import mosaic.config as cfg_mod
    from mosaic.config import API_KEY_PATHS, apply_api_keys

    cfg = cfg_mod.load()
    warnings: list[str] = []
    form = request.form

    # General settings
    dl_dir = form.get("download_dir", "").strip()
    if dl_dir:
        cfg["download_dir"] = dl_dir
    fn_pattern = form.get("filename_pattern", "").strip()
    if fn_pattern:
        cfg["filename_pattern"] = fn_pattern
    rate_limit = _form_number("rate_limit_delay", float, warnings, lo=0)
    if rate_limit is not None:
        cfg["rate_limit_delay"] = rate_limit

    # API keys — shared registry with CLI; empty keeps, clear_<name> removes
    apply_api_keys(cfg, {k: form.get(k, "").strip() for k, _ in API_KEY_PATHS})
    for name, path in API_KEY_PATHS:
        if form.get(f"clear_{name}") == "on":
            _set_path(cfg, path, "")

    # PMC shares the NCBI key
    ncbi_val = form.get("ncbi_key", "").strip()
    if ncbi_val:
        cfg.setdefault("sources", {}).setdefault("pmc", {})["api_key"] = ncbi_val
    elif form.get("clear_ncbi_key") == "on":
        cfg.setdefault("sources", {}).setdefault("pmc", {})["api_key"] = ""

    # Unpaywall email
    email = form.get("unpaywall_email", "").strip()
    if email:
        cfg.setdefault("unpaywall", {})["email"] = email

    # Zotero — discover the user ID like `mosaic config --zotero-key`
    zotero_key = form.get("zotero_key", "").strip()
    if zotero_key:
        from mosaic.workflows import configure_zotero_key

        warning = configure_zotero_key(cfg, zotero_key)
        if warning:
            warnings.append(warning)
    elif form.get("clear_zotero_key") == "on":
        cfg.setdefault("zotero", {}).update({"api_key": "", "user_id": 0})

    # Source toggles — only update if the form actually included the sources
    # section (HTML checkboxes are absent when unchecked; a hidden sentinel
    # field tells us the section was present in the submitted form).
    if form.get("_sources_section"):
        src_cfg = cfg.setdefault("sources", {})
        enabled_sources = form.getlist("enabled_sources")
        for cfg_key in set(SHORTHAND_TO_CFG_KEY.values()):
            src_cfg.setdefault(cfg_key, {})["enabled"] = cfg_key in enabled_sources

    # PEDro settings (separate from the enabled toggle)
    if form.get("_pedro_section"):
        pedro_cfg = cfg.setdefault("sources", {}).setdefault("pedro", {})
        pedro_cfg["acknowledge_fair_use"] = form.get("pedro_acknowledge_fair_use") == "on"
        pedro_cfg["fetch_details"] = form.get("pedro_fetch_details") == "on"
        pedro_delay = _form_number("pedro_rate_limit_delay", float, warnings, lo=0)
        if pedro_delay is not None:
            pedro_cfg["rate_limit_delay"] = pedro_delay

    # Obsidian
    if form.get("_obsidian_section"):
        obs = cfg.setdefault("obsidian", {})
        obs["vault_path"] = form.get("obsidian_vault_path", "").strip()
        obs["subfolder"] = form.get("obsidian_subfolder", "papers").strip()
        obs_pattern = form.get("obsidian_filename_pattern", "").strip()
        if obs_pattern:
            obs["filename_pattern"] = obs_pattern
        tags_raw = form.get("obsidian_tags", "paper").strip()
        obs["tags"] = [t.strip() for t in tags_raw.split(",") if t.strip()] or ["paper"]
        obs["wikilinks"] = form.get("obsidian_wikilinks") == "on"

    # LLM settings
    if form.get("_llm_section"):
        llm = cfg.setdefault("llm", {})
        llm["provider"] = form.get("llm_provider", "").strip()
        llm["model"] = form.get("llm_model", "").strip()
        llm["base_url"] = form.get("llm_base_url", "").strip()

    # RAG / embedding settings
    if form.get("_rag_section"):
        rag = cfg.setdefault("rag", {})
        rag["embedding_provider"] = form.get("rag_embedding_provider", "").strip()
        rag["embedding_model"] = form.get("rag_embedding_model", "").strip()
        rag["embedding_base_url"] = form.get("rag_embedding_base_url", "").strip()
        top_k = _form_number("rag_top_k", int, warnings, lo=1, hi=100)
        if top_k is not None:
            rag["top_k"] = top_k
        chunk_size = _form_number("rag_chunk_size", int, warnings, lo=64, hi=8192)
        if chunk_size is not None:
            rag["chunk_size"] = chunk_size
        overlap = _form_number("rag_chunk_overlap", int, warnings, lo=0)
        if overlap is not None:
            if overlap >= rag.get("chunk_size", 512):
                warnings.append(
                    "rag_chunk_overlap: must be smaller than the chunk size — not saved."
                )
            else:
                rag["chunk_overlap"] = overlap
        rag["auto_index"] = form.get("rag_auto_index") == "on"
        rag["full_text_index"] = form.get("rag_full_text_index") == "on"
        rag.setdefault("citations", {})["enabled"] = form.get("rag_citations_enabled") == "on"

    # Secrets that are not API_KEY_PATHS entries (Zotero handled above)
    for name, path in _SECRET_FIELDS.items():
        if name == "zotero_key":
            continue
        value = form.get(name, "").strip()
        if value:
            _set_path(cfg, path, value)
        elif form.get(f"clear_{name}") == "on":
            _set_path(cfg, path, "")

    # Advanced: db_path
    old_db_path = app_cfg().get("db_path")
    db_path = form.get("db_path", "").strip()
    if db_path:
        cfg["db_path"] = db_path

    cfg_mod.save(cfg)

    # Refresh app config (and the cache itself when the DB moved)
    current_app.config["MOSAIC_CFG"] = cfg
    if cfg.get("db_path") != old_db_path:
        from mosaic.db import Cache

        old_cache = current_app.config["MOSAIC_CACHE"]
        current_app.config["MOSAIC_CACHE"] = Cache(cfg["db_path"])
        old_cache.close()

    if request.headers.get("HX-Request"):
        html = '<article style="padding:.5rem 1rem;"><ins>Configuration saved.</ins>'
        if warnings:
            html += "<ul>" + "".join(f"<li>{escape(w)}</li>" for w in warnings) + "</ul>"
        return html + "</article>"

    flash("Configuration saved.", "success")
    for w in warnings:
        flash(w, "warning")
    return redirect(url_for("ui.config_page"))
