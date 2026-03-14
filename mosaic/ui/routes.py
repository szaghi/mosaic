"""Flask route handlers for the MOSAIC web UI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    stream_with_context,
    url_for,
)
from markupsafe import escape

from mosaic.models import Paper, SearchFilters
from mosaic.search import search_all
from mosaic.services import build_filters, filter_papers
from mosaic.source_registry import SHORTHAND_TO_CFG_KEY, SRC_MAP, build_sources

bp = Blueprint("ui", __name__)


# Maximum upload size (10 MB, enforced manually)
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg():
    return current_app.config["MOSAIC_CFG"]


def _cache():
    return current_app.config["MOSAIC_CACHE"]


def _jobs():
    return current_app.config["JOB_MANAGER"]


def _purge_stale():
    """Remove transient app.config keys for jobs that have been garbage-collected."""
    jm = _jobs()
    for jid in jm.stale_job_ids():
        current_app.config.pop(f"export_{jid}", None)
        current_app.config.pop(f"job_meta_{jid}", None)
    jm._cleanup()


def _version():
    from mosaic import __version__

    return __version__


def _safe_int(value, default: int = 10, lo: int = 1, hi: int = 200) -> int:
    """Parse an integer from form input, clamping to [lo, hi]."""
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def _build_filters(form) -> tuple[SearchFilters | None, str | None]:
    """Return (filters, optional_warning). Warning is set on invalid year format."""
    return build_filters(
        year=form.get("year", "").strip(),
        author=form.get("author", "").strip(),
        journal=form.get("journal", "").strip(),
        field=form.get("field", "all"),
        raw_query=form.get("raw_query", "").strip(),
    )


def _run_search(sources, query, max_per_source, filters, progress=None):
    """Executed in a worker thread."""
    errors: list[str] = []
    stats: dict = {}

    def _on_progress(source_name: str, status: str) -> None:
        if progress is not None:
            progress[source_name] = status

    papers = search_all(
        sources,
        query,
        max_per_source=max_per_source,
        filters=filters,
        errors=errors,
        stats=stats,
        progress_callback=_on_progress,
    )
    return {"papers": papers, "errors": errors, "stats": stats}


def _run_similar(identifier, max_results, oa_email, ss_api_key):
    """Executed in a worker thread."""
    from mosaic.similar import find_similar

    seed_title, papers = find_similar(
        identifier,
        max_results=max_results,
        oa_email=oa_email,
        ss_api_key=ss_api_key,
    )
    return {"seed_title": seed_title, "papers": papers}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@bp.route("/")
def search_page():
    cfg = _cfg()
    src_cfg = cfg.get("sources", {})
    # Build source list with enabled status
    source_list = []
    for key, display_name in SRC_MAP.items():
        cfg_key = SHORTHAND_TO_CFG_KEY.get(key, key)
        enabled = src_cfg.get(cfg_key, {}).get("enabled", True)
        source_list.append({"key": key, "name": display_name, "enabled": enabled})

    prefill_query = request.args.get("q", "")
    prefill_filters = {
        "year": request.args.get("year", ""),
        "author": request.args.get("author", ""),
        "journal": request.args.get("journal", ""),
        "field": request.args.get("field", ""),
    }
    return render_template(
        "search.html",
        sources=source_list,
        version=_version(),
        prefill_query=prefill_query,
        prefill_filters=prefill_filters,
    )


@bp.route("/search", methods=["POST"])
def search_submit():
    _purge_stale()
    cfg = _cfg()
    query = request.form.get("query", "").strip()
    if not query:
        return render_template(
            "partials/results.html",
            papers=[],
            errors=["Please enter a search query."],
            stats={},
            version=_version(),
        )

    max_results = _safe_int(request.form.get("max_results", 10))
    filters, year_warning = _build_filters(request.form)

    # Build sources filtered by user selection
    selected = request.form.getlist("sources")
    all_sources = build_sources(cfg)
    if selected:
        selected_names = {SRC_MAP[k] for k in selected if k in SRC_MAP}
        sources = [s for s in all_sources if s.name in selected_names]
    elif request.form.get("_has_sources"):
        # User explicitly deselected all sources in the search form
        errors = ["No sources selected. Please select at least one source."]
        if year_warning:
            errors.insert(0, year_warning)
        return render_template(
            "partials/results.html", papers=[], errors=errors, stats={}, version=_version()
        )
    else:
        sources = all_sources

    source_count = len(sources)
    # Shared dict — written by _run_search worker, read by job_status polling
    progress: dict[str, str] = {s.name: "pending" for s in sources}
    jm = _jobs()
    job_id = jm.submit(_run_search, sources, query, max_results, filters, progress)
    job = jm.get(job_id)
    if job is not None:
        job.progress = progress

    # Store form state for the export link and history re-run
    current_app.config[f"job_meta_{job_id}"] = {
        "query": query,
        "oa_only": request.form.get("oa_only") == "on",
        "pdf_only": request.form.get("pdf_only") == "on",
        "sort_by": request.form.get("sort_by", ""),
        "year_warning": year_warning,
        "filters": {
            "year": request.form.get("year", ""),
            "author": request.form.get("author", ""),
            "journal": request.form.get("journal", ""),
            "field": request.form.get("field", "all"),
        },
    }

    return render_template(
        "partials/job_status.html",
        job_id=job_id,
        source_count=source_count,
        status_url=url_for("ui.search_status", job_id=job_id),
        job_type="search",
        progress=progress,
    )


@bp.route("/search/status/<job_id>")
def search_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return render_template(
            "partials/results.html",
            papers=[],
            errors=["Job not found."],
            stats={},
            version=_version(),
        )

    if job.status == "running":
        return render_template(
            "partials/job_status.html",
            job_id=job_id,
            source_count=0,
            status_url=url_for("ui.search_status", job_id=job_id),
            job_type="search",
            progress=job.progress,
        )

    if job.status == "error":
        _jobs().pop(job_id)
        return render_template(
            "partials/results.html",
            papers=[],
            errors=[job.error_message],
            stats={},
            version=_version(),
        )

    # Done
    result = job.result
    papers = result["papers"]
    errors = result["errors"]
    stats = result["stats"]

    # Apply post-filters from form state
    meta = current_app.config.pop(f"job_meta_{job_id}", {})
    if meta.get("year_warning"):
        errors.insert(0, meta["year_warning"])
    papers = filter_papers(
        papers,
        oa_only=meta.get("oa_only", False),
        pdf_only=meta.get("pdf_only", False),
        sort_by=meta.get("sort_by", ""),
    )

    # Save to cache and record search history
    cache = _cache()
    for p in papers:
        cache.save(p)
    cache.save_search(
        query=meta.get("query", ""),
        filters_json=json.dumps(meta.get("filters", {})),
        result_count=len(papers),
    )

    # Store papers for export
    current_app.config[f"export_{job_id}"] = papers

    return render_template(
        "partials/results.html",
        papers=papers,
        errors=errors,
        stats=stats,
        job_id=job_id,
        version=_version(),
    )


@bp.route("/stream/<job_id>")
def stream_job(job_id):
    """SSE endpoint — pushes progress updates until the job finishes."""

    def _generate():
        job = _jobs().get(job_id)
        if job is None:
            yield "event: done\ndata: {}\n\n"
            return
        while True:
            done = job.wait(timeout=1.0)
            progress_json = json.dumps(job.progress)
            yield f"event: progress\ndata: {progress_json}\n\n"
            if done or job.status != "running":
                yield "event: done\ndata: {}\n\n"
                return

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/paper/<path:uid>")
def paper_detail(uid):
    uid = unquote(uid)
    paper = _cache().get_by_uid(uid)
    if paper is None:
        flash("Paper not found in cache.", "warning")
        return redirect(url_for("ui.search_page"))

    dl = _cache().get_download(uid)
    download_status = None
    if dl:
        download_status = {"path": dl["local_path"], "status": dl["status"]}

    return render_template(
        "detail.html", paper=paper, download_status=download_status, version=_version(), quote=quote
    )


def _run_download(uid, cfg, db_path):
    """Executed in a worker thread."""
    from mosaic.db import Cache
    from mosaic.downloader import download as dl_paper

    cache = Cache(db_path)
    paper = cache.get_by_uid(uid)
    if paper is None:
        return {"ok": False, "msg": "Paper not found."}

    path = dl_paper(
        paper,
        cfg["download_dir"],
        cache,
        cfg.get("unpaywall", {}).get("email", ""),
        cfg.get("filename_pattern", "{year}_{source}_{author}_{title}"),
    )
    if path:
        return {"ok": True, "msg": f"PDF saved: {Path(path).name}"}
    return {"ok": False, "msg": "Could not find a downloadable PDF."}


@bp.route("/download/<path:uid>", methods=["POST"])
def download_paper(uid):
    uid = unquote(uid)
    paper = _cache().get_by_uid(uid)
    if paper is None:
        return "<p>Paper not found.</p>", 404

    cfg = _cfg()
    job_id = _jobs().submit(_run_download, uid, cfg, cfg["db_path"])
    status_url = url_for("ui.download_status", job_id=job_id)
    return (
        f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#download-status" hx-swap="innerHTML">'
        f'<span aria-busy="true">Downloading&hellip;</span></div>'
    )


@bp.route("/download/status/<job_id>")
def download_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<mark>Download job not found.</mark>"

    if job.status == "running":
        status_url = url_for("ui.download_status", job_id=job_id)
        return (
            f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#download-status" hx-swap="innerHTML">'
            f'<span aria-busy="true">Downloading&hellip;</span></div>'
        )

    _jobs().pop(job_id)
    if job.status == "error":
        return f"<mark>Download failed: {escape(job.error_message)}</mark>"

    result = job.result
    return f"<mark>{escape(result['msg'])}</mark>"


# ---------------------------------------------------------------------------
# Similar
# ---------------------------------------------------------------------------


@bp.route("/similar")
def similar_page():
    identifier = request.args.get("identifier", "")
    return render_template("similar.html", identifier=identifier, version=_version())


@bp.route("/similar", methods=["POST"])
def similar_submit():
    _purge_stale()
    identifier = request.form.get("identifier", "").strip()
    if not identifier:
        return render_template(
            "partials/results.html",
            papers=[],
            errors=["Please enter a DOI or arXiv ID."],
            stats={},
            version=_version(),
        )

    max_results = _safe_int(request.form.get("max_results", 10))
    cfg = _cfg()
    oa_email = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key = cfg.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")

    job_id = _jobs().submit(_run_similar, identifier, max_results, oa_email, ss_api_key)
    current_app.config[f"job_meta_{job_id}"] = {
        "oa_only": request.form.get("oa_only") == "on",
        "pdf_only": request.form.get("pdf_only") == "on",
        "sort_by": request.form.get("sort_by", ""),
    }

    return render_template(
        "partials/job_status.html",
        job_id=job_id,
        source_count=2,
        status_url=url_for("ui.similar_status", job_id=job_id),
        job_type="similar",
    )


@bp.route("/similar/status/<job_id>")
def similar_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return render_template(
            "partials/results.html",
            papers=[],
            errors=["Job not found."],
            stats={},
            version=_version(),
        )

    if job.status == "running":
        return render_template(
            "partials/job_status.html",
            job_id=job_id,
            source_count=2,
            status_url=url_for("ui.similar_status", job_id=job_id),
            job_type="similar",
        )

    if job.status == "error":
        _jobs().pop(job_id)
        return render_template(
            "partials/results.html",
            papers=[],
            errors=[job.error_message],
            stats={},
            version=_version(),
        )

    result = job.result
    papers = result["papers"]
    seed_title = result.get("seed_title")

    meta = current_app.config.pop(f"job_meta_{job_id}", {})
    papers = filter_papers(
        papers,
        oa_only=meta.get("oa_only", False),
        pdf_only=meta.get("pdf_only", False),
        sort_by=meta.get("sort_by", ""),
    )

    cache = _cache()
    for p in papers:
        cache.save(p)

    current_app.config[f"export_{job_id}"] = papers

    return render_template(
        "partials/results.html",
        papers=papers,
        errors=[],
        stats={},
        seed_title=seed_title,
        job_id=job_id,
        version=_version(),
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@bp.route("/config")
def config_page():
    import mosaic.config as cfg_mod

    cfg = cfg_mod.load()
    return render_template("config.html", cfg=cfg, version=_version())


@bp.route("/config", methods=["POST"])
def config_save():
    import mosaic.config as cfg_mod

    cfg = cfg_mod.load()

    # General settings
    dl_dir = request.form.get("download_dir", "").strip()
    if dl_dir:
        cfg["download_dir"] = dl_dir
    fn_pattern = request.form.get("filename_pattern", "").strip()
    if fn_pattern:
        cfg["filename_pattern"] = fn_pattern
    rate_limit = request.form.get("rate_limit_delay", "").strip()
    if rate_limit:
        try:
            cfg["rate_limit_delay"] = float(rate_limit)
        except ValueError:
            pass

    # API keys — shared registry with CLI
    from mosaic.config import API_KEY_PATHS, apply_api_keys

    apply_api_keys(cfg, {k: request.form.get(k, "") for k, _ in API_KEY_PATHS})

    # Also set PMC key to same as PubMed NCBI key
    ncbi_val = request.form.get("ncbi_key", "").strip()
    if ncbi_val:
        cfg.setdefault("sources", {}).setdefault("pmc", {})["api_key"] = ncbi_val

    # Unpaywall email
    email = request.form.get("unpaywall_email", "").strip()
    if email:
        cfg.setdefault("unpaywall", {})["email"] = email

    # Zotero
    zotero_key = request.form.get("zotero_key", "").strip()
    if zotero_key:
        cfg.setdefault("zotero", {})["api_key"] = zotero_key

    # Source toggles — only update if the form actually included the sources
    # section (HTML checkboxes are absent when unchecked; a hidden sentinel
    # field tells us the section was present in the submitted form).
    if request.form.get("_sources_section"):
        src_cfg = cfg.get("sources", {})
        all_cfg_keys = set(SHORTHAND_TO_CFG_KEY.values())
        enabled_sources = request.form.getlist("enabled_sources")
        for cfg_key in all_cfg_keys:
            src_cfg.setdefault(cfg_key, {})["enabled"] = cfg_key in enabled_sources

    # PEDro settings (separate from the enabled toggle)
    if request.form.get("_pedro_section"):
        pedro_cfg = cfg.setdefault("sources", {}).setdefault("pedro", {})
        pedro_cfg["acknowledge_fair_use"] = request.form.get("pedro_acknowledge_fair_use") == "on"
        pedro_cfg["fetch_details"] = request.form.get("pedro_fetch_details") == "on"
        pedro_delay = request.form.get("pedro_rate_limit_delay", "").strip()
        if pedro_delay:
            try:
                pedro_cfg["rate_limit_delay"] = float(pedro_delay)
            except ValueError:
                pass

    # Obsidian
    if request.form.get("_obsidian_section"):
        obs = cfg.setdefault("obsidian", {})
        vault_path = request.form.get("obsidian_vault_path", "").strip()
        obs["vault_path"] = vault_path
        subfolder = request.form.get("obsidian_subfolder", "papers").strip()
        obs["subfolder"] = subfolder
        fn_pattern = request.form.get("obsidian_filename_pattern", "").strip()
        if fn_pattern:
            obs["filename_pattern"] = fn_pattern
        tags_raw = request.form.get("obsidian_tags", "paper").strip()
        obs["tags"] = [t.strip() for t in tags_raw.split(",") if t.strip()] or ["paper"]
        obs["wikilinks"] = request.form.get("obsidian_wikilinks") == "on"

    cfg_mod.save(cfg)

    # Refresh app config
    current_app.config["MOSAIC_CFG"] = cfg

    if request.headers.get("HX-Request"):
        return '<article style="padding:.5rem 1rem;"><ins>Configuration saved.</ins></article>'

    flash("Configuration saved.", "success")
    return redirect(url_for("ui.config_page"))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@bp.route("/export/<job_id>")
def export_results(job_id):
    fmt = request.args.get("format", "csv")
    papers = current_app.config.get(f"export_{job_id}")
    if not papers:
        flash("Export results have expired. Please re-run your search.", "warning")
        return redirect(url_for("ui.search_page"))

    from mosaic.exporter import export

    ext_map = {"csv": ".csv", "json": ".json", "bib": ".bib", "md": ".md"}
    ext = ext_map.get(fmt, ".csv")
    mime_map = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".bib": "application/x-bibtex",
        ".md": "text/markdown",
    }

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    export(papers, tmp_path)
    return send_file(
        tmp_path,
        mimetype=mime_map.get(ext, "text/plain"),
        as_attachment=True,
        download_name=f"mosaic_results{ext}",
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@bp.route("/history")
def history_page():
    searches = _cache().list_searches(limit=50)
    for s in searches:
        try:
            s["filters"] = json.loads(s.get("filters_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            s["filters"] = {}
    return render_template("history.html", searches=searches, version=_version())


# ---------------------------------------------------------------------------
# Zotero export
# ---------------------------------------------------------------------------


def _run_zotero_export(papers_data, cfg, collection_name):
    """Executed in a worker thread."""
    from mosaic.workflows import push_to_zotero

    papers = [Paper.from_dict(d) for d in papers_data]
    return push_to_zotero(papers, cfg, collection_name=collection_name)


@bp.route("/zotero/export/<job_id>", methods=["POST"])
def zotero_export(job_id):
    papers = current_app.config.get(f"export_{job_id}")
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"

    cfg = _cfg()
    collection_name = request.form.get("zotero_collection", "").strip()

    # Serialise Paper objects for the worker thread
    papers_data = [p.to_dict() for p in papers]
    zot_job_id = _jobs().submit(_run_zotero_export, papers_data, cfg, collection_name)
    status_url = url_for("ui.zotero_export_status", job_id=zot_job_id)
    return (
        f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#zotero-status" hx-swap="innerHTML">'
        f'<span aria-busy="true">Sending to Zotero&hellip;</span></div>'
    )


@bp.route("/zotero/export/status/<job_id>")
def zotero_export_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<mark>Zotero export job not found.</mark>"
    if job.status == "running":
        status_url = url_for("ui.zotero_export_status", job_id=job_id)
        return (
            f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#zotero-status" hx-swap="innerHTML">'
            f'<span aria-busy="true">Sending to Zotero&hellip;</span></div>'
        )
    _jobs().pop(job_id)
    if job.status == "error":
        return f"<mark>Zotero export failed: {escape(job.error_message)}</mark>"
    result = job.result
    if result["ok"]:
        return f"<ins>{escape(result['msg'])}</ins>"
    return f"<mark>{escape(result['msg'])}</mark>"


@bp.route("/zotero/paper/<path:uid>", methods=["POST"])
def zotero_export_paper(uid):
    uid = unquote(uid)
    paper = _cache().get_by_uid(uid)
    if paper is None:
        return "<mark>Paper not found.</mark>"

    cfg = _cfg()
    collection_name = request.form.get("zotero_collection", "").strip()
    papers_data = [paper.to_dict()]
    zot_job_id = _jobs().submit(_run_zotero_export, papers_data, cfg, collection_name)
    status_url = url_for("ui.zotero_export_status", job_id=zot_job_id)
    return (
        f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#zotero-status" hx-swap="innerHTML">'
        f'<span aria-busy="true">Sending to Zotero&hellip;</span></div>'
    )


# ---------------------------------------------------------------------------
# Obsidian export
# ---------------------------------------------------------------------------


def _run_obsidian_export(papers_data, cfg):
    """Executed in a worker thread."""
    from mosaic.workflows import push_to_obsidian

    papers = [Paper.from_dict(d) for d in papers_data]
    return push_to_obsidian(papers, cfg)


@bp.route("/obsidian/export/<job_id>", methods=["POST"])
def obsidian_export(job_id):
    papers = current_app.config.get(f"export_{job_id}")
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"

    cfg = _cfg()
    papers_data = [p.to_dict() for p in papers]
    obs_job_id = _jobs().submit(_run_obsidian_export, papers_data, cfg)
    status_url = url_for("ui.obsidian_export_status", job_id=obs_job_id)
    return (
        f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#obsidian-status" hx-swap="innerHTML">'
        f'<span aria-busy="true">Exporting to Obsidian&hellip;</span></div>'
    )


@bp.route("/obsidian/export/status/<job_id>")
def obsidian_export_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<mark>Obsidian export job not found.</mark>"
    if job.status == "running":
        status_url = url_for("ui.obsidian_export_status", job_id=job_id)
        return (
            f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#obsidian-status" hx-swap="innerHTML">'
            f'<span aria-busy="true">Exporting to Obsidian&hellip;</span></div>'
        )
    _jobs().pop(job_id)
    if job.status == "error":
        return f"<mark>Obsidian export failed: {escape(job.error_message)}</mark>"
    result = job.result
    if result["ok"]:
        return f"<ins>{escape(result['msg'])}</ins>"
    return f"<mark>{escape(result['msg'])}</mark>"


# ---------------------------------------------------------------------------
# NotebookLM
# ---------------------------------------------------------------------------


def _run_notebook_from_query(name, query, max_results, filters, oa_only, pdf_only, artifacts, cfg):
    """Executed in a worker thread — search → download → create notebook."""
    import asyncio

    from mosaic.db import Cache
    from mosaic.downloader import download as dl_paper
    from mosaic.notebooklm_bridge import _require_notebooklm, create_notebook

    _require_notebooklm()

    sources = build_sources(cfg)
    errors: list[str] = []
    papers = search_all(sources, query, max_per_source=max_results, filters=filters, errors=errors)
    papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only)

    if not papers:
        return {"ok": False, "msg": "No papers found for this query."}

    cache = Cache(cfg["db_path"])
    email = cfg.get("unpaywall", {}).get("email", "")
    dl_dir = cfg["download_dir"]
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")

    papers_with_paths = []
    for p in papers:
        path = dl_paper(p, dl_dir, cache, email, pattern)
        papers_with_paths.append((p, Path(path) if path else None))

    nb_id = asyncio.run(create_notebook(name, papers_with_paths, artifacts=artifacts))
    added = sum(1 for _, path in papers_with_paths if path)
    return {
        "ok": True,
        "nb_id": nb_id,
        "paper_count": len(papers),
        "downloaded": added,
    }


def _run_notebook_from_dir(name, from_dir, artifacts, cfg):
    """Executed in a worker thread — import PDFs from directory."""
    import asyncio

    from mosaic.notebooklm_bridge import _require_notebooklm, create_notebook_from_dir

    _require_notebooklm()

    directory = Path(from_dir).expanduser()
    if not directory.is_dir():
        return {"ok": False, "msg": f"Directory not found: {from_dir}"}

    try:
        nb_id = asyncio.run(create_notebook_from_dir(name, directory, artifacts=artifacts))
    except ValueError as e:
        return {"ok": False, "msg": str(e)}

    return {"ok": True, "nb_id": nb_id}


@bp.route("/notebook")
def notebook_page():
    from mosaic.notebooklm_bridge import check_notebooklm_status

    nb_status = check_notebooklm_status()
    return render_template("notebook.html", version=_version(), nb_status=nb_status)


@bp.route("/notebook", methods=["POST"])
def notebook_submit():
    _purge_stale()
    name = request.form.get("name", "").strip()
    if not name:
        return "<article>Please enter a notebook name.</article>"

    input_mode = request.form.get("input_mode", "query")
    artifacts: set[str] = set(request.form.getlist("artifacts"))
    cfg = _cfg()

    if input_mode == "dir":
        from_dir = request.form.get("from_dir", "").strip()
        if not from_dir:
            return "<article>Please enter a PDF directory path.</article>"
        job_id = _jobs().submit(_run_notebook_from_dir, name, from_dir, artifacts, cfg)
    else:
        query = request.form.get("query", "").strip()
        if not query:
            return "<article>Please enter a search query.</article>"
        max_results = _safe_int(request.form.get("max_results", 10))
        filters, year_warning = _build_filters(request.form)
        if year_warning:
            return f"<article>{year_warning}</article>"
        oa_only = request.form.get("oa_only") == "on"
        pdf_only = request.form.get("pdf_only") == "on"
        job_id = _jobs().submit(
            _run_notebook_from_query,
            name,
            query,
            max_results,
            filters,
            oa_only,
            pdf_only,
            artifacts,
            cfg,
        )

    status_url = url_for("ui.notebook_status", job_id=job_id)
    return (
        f'<div hx-get="{status_url}" hx-trigger="every 2s" hx-target="#nb-results" hx-swap="innerHTML">'
        f'<article aria-busy="true">Creating notebook <strong>{escape(name)}</strong>&hellip; '
        f"(this may take a minute)</article></div>"
    )


@bp.route("/notebook/status/<job_id>")
def notebook_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"

    if job.status == "running":
        status_url = url_for("ui.notebook_status", job_id=job_id)
        return (
            f'<div hx-get="{status_url}" hx-trigger="every 2s" hx-target="#nb-results" hx-swap="innerHTML">'
            f'<article aria-busy="true">Creating notebook&hellip; (this may take a minute)</article></div>'
        )

    _jobs().pop(job_id)
    if job.status == "error":
        return (
            f"<article><mark>Notebook creation failed: {escape(job.error_message)}</mark></article>"
        )

    result = job.result
    if not result["ok"]:
        return f"<article><mark>{escape(result['msg'])}</mark></article>"

    nb_id = result["nb_id"]
    nb_url = f"https://notebooklm.google.com/notebook/{nb_id}"
    lines = ["<ins>Notebook created successfully!</ins>"]
    if "paper_count" in result:
        lines.append(
            f"<p>{result['paper_count']} paper(s) found, {result['downloaded']} PDF(s) added.</p>"
        )
    lines.append(
        f'<p><a href="{nb_url}" target="_blank" rel="noopener">Open in NotebookLM &rarr;</a></p>'
    )
    return "".join(lines)


# ---------------------------------------------------------------------------
# Bulk download
# ---------------------------------------------------------------------------


@bp.route("/bulk")
def bulk_page():
    return render_template("bulk.html", version=_version())


def _run_bulk_download(dois, cfg, db_path):
    """Executed in a worker thread."""
    from mosaic.db import Cache
    from mosaic.downloader import download as dl_paper

    cache = Cache(db_path)
    email = cfg.get("unpaywall", {}).get("email", "")
    download_dir = cfg["download_dir"]
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")
    ok = fail = 0
    results = []

    for doi in dois:
        paper = Paper(title=doi, doi=doi, source="manual")
        path = dl_paper(paper, download_dir, cache, email, pattern)
        if path:
            ok += 1
            results.append({"doi": doi, "status": "ok", "path": Path(path).name})
        else:
            fail += 1
            results.append({"doi": doi, "status": "fail", "path": ""})

    return {"ok": ok, "fail": fail, "results": results}


@bp.route("/bulk", methods=["POST"])
def bulk_submit():
    _purge_stale()

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return "<article>Please select a .bib or .csv file.</article>"

    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in (".bib", ".csv"):
        return "<article>Unsupported file type. Use .bib or .csv.</article>"

    # Save to a temp file for processing
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = uploaded.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            return "<article>File too large (max 10 MB).</article>"
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from mosaic.bulk import read_dois

        dois = read_dois(tmp_path)
    except ValueError as e:
        return f"<article>{e}</article>"
    finally:
        tmp_path.unlink(missing_ok=True)

    if not dois:
        return "<article>No DOIs found in the uploaded file.</article>"

    cfg = _cfg()
    job_id = _jobs().submit(_run_bulk_download, dois, cfg, cfg["db_path"])
    current_app.config[f"job_meta_{job_id}"] = {"doi_count": len(dois)}

    status_url = url_for("ui.bulk_status", job_id=job_id)
    return (
        f'<div hx-get="{status_url}" hx-trigger="every 2s" hx-target="#results" hx-swap="innerHTML">'
        f'<article aria-busy="true">Downloading {len(dois)} DOI(s)&hellip;</article></div>'
    )


@bp.route("/bulk/status/<job_id>")
def bulk_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"

    if job.status == "running":
        meta = current_app.config.get(f"job_meta_{job_id}", {})
        count = meta.get("doi_count", "?")
        status_url = url_for("ui.bulk_status", job_id=job_id)
        return (
            f'<div hx-get="{status_url}" hx-trigger="every 2s" hx-target="#results" hx-swap="innerHTML">'
            f'<article aria-busy="true">Downloading {count} DOI(s)&hellip;</article></div>'
        )

    current_app.config.pop(f"job_meta_{job_id}", None)
    _jobs().pop(job_id)

    if job.status == "error":
        return f"<article>Bulk download failed: {escape(job.error_message)}</article>"

    result = job.result
    html = f"<p><strong>Done:</strong> {result['ok']} downloaded, {result['fail']} failed.</p>"
    if result["results"]:
        html += '<table role="grid"><thead><tr><th>DOI</th><th>Status</th><th>File</th></tr></thead><tbody>'
        for r in result["results"]:
            icon = (
                '<span class="badge-oa">&#10003;</span>'
                if r["status"] == "ok"
                else '<span class="badge-closed">&#10007;</span>'
            )
            html += (
                f"<tr><td>{escape(r['doi'])}</td><td>{icon}</td><td>{escape(r['path'])}</td></tr>"
            )
        html += "</tbody></table>"
    return html


# ---------------------------------------------------------------------------
# Auth sessions
# ---------------------------------------------------------------------------


@bp.route("/sessions")
def sessions_page():
    from mosaic.auth import list_sessions

    sessions = list_sessions()
    return render_template("sessions.html", sessions=sessions, version=_version())


@bp.route("/sessions/delete/<name>", methods=["POST"])
def session_delete(name):
    from mosaic.auth import delete_session

    if delete_session(name):
        flash(f"Session '{name}' deleted.", "success")
    else:
        flash(f"No session found for '{name}'.", "warning")
    return redirect(url_for("ui.sessions_page"))
