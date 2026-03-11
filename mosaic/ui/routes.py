"""Flask route handlers for the MOSAIC web UI."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

from flask import (
    Blueprint, Response, current_app, flash, redirect, render_template,
    request, send_file, stream_with_context, url_for,
)

from mosaic.helpers import SRC_MAP, build_sources
from mosaic.models import Paper, SearchFilters
from mosaic.search import search_all

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


def _build_filters(form) -> SearchFilters | None:
    year = form.get("year", "").strip()
    author = form.get("author", "").strip()
    journal = form.get("journal", "").strip()
    field = form.get("field", "all")
    raw_query = form.get("raw_query", "").strip()

    if not any([year, author, journal, field != "all", raw_query]):
        return None

    authors = [a.strip() for a in author.split(",") if a.strip()] if author else []
    filters = SearchFilters(authors=authors, journal=journal, field=field, raw_query=raw_query)

    if year:
        try:
            parsed = SearchFilters.parse_year(year)
            filters.year_from = parsed.year_from
            filters.year_to = parsed.year_to
            filters.years = parsed.years
        except ValueError:
            pass  # silently ignore bad year format in UI

    return filters


def _run_search(sources, query, max_per_source, filters, progress=None):
    """Executed in a worker thread."""
    errors: list[str] = []
    stats: dict = {}

    def _on_progress(source_name: str, status: str) -> None:
        if progress is not None:
            progress[source_name] = status

    papers = search_all(
        sources, query,
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
        # Map shorthand to config key
        cfg_key_map = {
            "arxiv": "arxiv", "ss": "semantic_scholar", "sd": "sciencedirect",
            "doaj": "doaj", "epmc": "europepmc", "oa": "openalex",
            "base": "base", "core": "core", "sp": "springer",
            "springer": "springer_api", "ads": "nasa_ads", "ieee": "ieee",
            "zenodo": "zenodo", "crossref": "crossref", "dblp": "dblp",
            "hal": "hal", "pubmed": "pubmed", "pmc": "pmc", "rxiv": "biorxiv",
        }
        cfg_key = cfg_key_map.get(key, key)
        enabled = src_cfg.get(cfg_key, {}).get("enabled", True)
        source_list.append({"key": key, "name": display_name, "enabled": enabled})

    prefill_query = request.args.get("q", "")
    return render_template("search.html", sources=source_list, version=_version(), prefill_query=prefill_query)


@bp.route("/search", methods=["POST"])
def search_submit():
    _purge_stale()
    cfg = _cfg()
    query = request.form.get("query", "").strip()
    if not query:
        return render_template("partials/results.html", papers=[], errors=["Please enter a search query."], stats={}, version=_version())

    max_results = int(request.form.get("max_results", 10))
    filters = _build_filters(request.form)

    # Build sources filtered by user selection
    selected = request.form.getlist("sources")
    all_sources = build_sources(cfg)
    if selected:
        selected_names = {SRC_MAP[k] for k in selected if k in SRC_MAP}
        sources = [s for s in all_sources if s.name in selected_names]
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

    # Store form state for the export link later
    current_app.config[f"job_meta_{job_id}"] = {
        "query": query,
        "oa_only": request.form.get("oa_only") == "on",
        "pdf_only": request.form.get("pdf_only") == "on",
        "sort_by": request.form.get("sort_by", ""),
    }

    return render_template("partials/job_status.html",
                           job_id=job_id, source_count=source_count,
                           status_url=url_for("ui.search_status", job_id=job_id),
                           job_type="search", progress=progress)


@bp.route("/search/status/<job_id>")
def search_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return render_template("partials/results.html", papers=[], errors=["Job not found."], stats={}, version=_version())

    if job.status == "running":
        return render_template("partials/job_status.html",
                               job_id=job_id, source_count=0,
                               status_url=url_for("ui.search_status", job_id=job_id),
                               job_type="search", progress=job.progress)

    if job.status == "error":
        _jobs().pop(job_id)
        return render_template("partials/results.html", papers=[], errors=[job.error_message], stats={}, version=_version())

    # Done
    result = job.result
    papers = result["papers"]
    errors = result["errors"]
    stats = result["stats"]

    # Apply post-filters from form state
    meta = current_app.config.pop(f"job_meta_{job_id}", {})
    if meta.get("oa_only"):
        papers = [p for p in papers if p.is_open_access or p.pdf_url]
    if meta.get("pdf_only"):
        papers = [p for p in papers if p.pdf_url]
    sort_by = meta.get("sort_by", "")
    if sort_by == "citations":
        papers.sort(key=lambda p: p.citation_count or 0, reverse=True)
    elif sort_by == "year":
        papers.sort(key=lambda p: p.year or 0, reverse=True)

    # Save to cache and record search history
    cache = _cache()
    for p in papers:
        cache.save(p)
    cache.save_search(
        query=meta.get("query", ""),
        result_count=len(papers),
    )

    # Store papers for export
    current_app.config[f"export_{job_id}"] = papers

    return render_template("partials/results.html",
                           papers=papers, errors=errors, stats=stats,
                           job_id=job_id, version=_version())


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

    return render_template("detail.html", paper=paper, download_status=download_status,
                           version=_version(), quote=quote)


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
        return f"<mark>Download failed: {job.error_message}</mark>"

    result = job.result
    return f'<mark>{result["msg"]}</mark>'


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
        return render_template("partials/results.html", papers=[], errors=["Please enter a DOI or arXiv ID."], stats={}, version=_version())

    max_results = int(request.form.get("max_results", 10))
    cfg = _cfg()
    oa_email = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key = cfg.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")

    job_id = _jobs().submit(_run_similar, identifier, max_results, oa_email, ss_api_key)
    current_app.config[f"job_meta_{job_id}"] = {
        "oa_only": request.form.get("oa_only") == "on",
        "pdf_only": request.form.get("pdf_only") == "on",
        "sort_by": request.form.get("sort_by", ""),
    }

    return render_template("partials/job_status.html",
                           job_id=job_id, source_count=2,
                           status_url=url_for("ui.similar_status", job_id=job_id),
                           job_type="similar")


@bp.route("/similar/status/<job_id>")
def similar_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return render_template("partials/results.html", papers=[], errors=["Job not found."], stats={}, version=_version())

    if job.status == "running":
        return render_template("partials/job_status.html",
                               job_id=job_id, source_count=2,
                               status_url=url_for("ui.similar_status", job_id=job_id),
                               job_type="similar")

    if job.status == "error":
        _jobs().pop(job_id)
        return render_template("partials/results.html", papers=[], errors=[job.error_message], stats={}, version=_version())

    result = job.result
    papers = result["papers"]
    seed_title = result.get("seed_title")

    meta = current_app.config.pop(f"job_meta_{job_id}", {})
    if meta.get("oa_only"):
        papers = [p for p in papers if p.is_open_access or p.pdf_url]
    if meta.get("pdf_only"):
        papers = [p for p in papers if p.pdf_url]
    sort_by = meta.get("sort_by", "")
    if sort_by == "citations":
        papers.sort(key=lambda p: p.citation_count or 0, reverse=True)
    elif sort_by == "year":
        papers.sort(key=lambda p: p.year or 0, reverse=True)

    cache = _cache()
    for p in papers:
        cache.save(p)

    current_app.config[f"export_{job_id}"] = papers

    return render_template("partials/results.html",
                           papers=papers, errors=[], stats={},
                           seed_title=seed_title, job_id=job_id,
                           version=_version())


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

    # API keys
    for key_name, cfg_path in [
        ("elsevier_key", ("sources", "sciencedirect", "api_key")),
        ("ss_key", ("sources", "semantic_scholar", "api_key")),
        ("core_key", ("sources", "core", "api_key")),
        ("ads_key", ("sources", "nasa_ads", "api_key")),
        ("ieee_key", ("sources", "ieee", "api_key")),
        ("ncbi_key", ("sources", "pubmed", "api_key")),
        ("springer_key", ("sources", "springer_api", "api_key")),
    ]:
        val = request.form.get(key_name, "").strip()
        if val:
            d = cfg
            for part in cfg_path[:-1]:
                d = d.setdefault(part, {})
            d[cfg_path[-1]] = val

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
        cfg_key_map = {
            "arxiv": "arxiv", "semantic_scholar": "semantic_scholar",
            "sciencedirect": "sciencedirect", "doaj": "doaj",
            "europepmc": "europepmc", "openalex": "openalex",
            "base": "base", "core": "core", "springer": "springer",
            "springer_api": "springer_api", "nasa_ads": "nasa_ads",
            "ieee": "ieee", "zenodo": "zenodo", "crossref": "crossref",
            "dblp": "dblp", "hal": "hal", "pubmed": "pubmed",
            "pmc": "pmc", "biorxiv": "biorxiv",
        }
        enabled_sources = request.form.getlist("enabled_sources")
        for cfg_key in cfg_key_map.values():
            src_cfg.setdefault(cfg_key, {})["enabled"] = cfg_key in enabled_sources

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
        flash("No results to export. Run a search first.", "warning")
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
    return render_template("history.html", searches=searches, version=_version())


# ---------------------------------------------------------------------------
# Zotero export
# ---------------------------------------------------------------------------

def _run_zotero_export(papers_data, cfg, collection_name):
    """Executed in a worker thread."""
    from mosaic.zotero import ZoteroClient

    zot_cfg = cfg.get("zotero", {})
    api_key = zot_cfg.get("api_key", "")
    user_id = zot_cfg.get("user_id", 0)
    client = ZoteroClient(api_key=api_key, user_id=user_id)

    if not client.is_reachable():
        if api_key:
            return {"ok": False, "msg": "Zotero web API not reachable. Check your API key in Config."}
        return {"ok": False, "msg": "No Zotero API key configured and Zotero desktop is not running. "
                "Either set a Zotero web API key in Config, or start the Zotero desktop app."}

    collection_key = None
    if collection_name:
        try:
            collection_key = client.ensure_collection(collection_name)
        except Exception as e:
            return {"ok": False, "msg": f"Could not create/find collection '{collection_name}': {e}"}

    # Reconstruct Paper objects from serialised data
    papers = [Paper(**d) for d in papers_data]
    item_keys = client.add_papers(papers, collection_key=collection_key)
    added = sum(1 for k in item_keys if k)
    label = f" to '{collection_name}'" if collection_name else ""
    return {"ok": True, "msg": f"{added} paper(s) added to Zotero{label}."}


@bp.route("/zotero/export/<job_id>", methods=["POST"])
def zotero_export(job_id):
    papers = current_app.config.get(f"export_{job_id}")
    if not papers:
        return "<mark>No results to export. Run a search first.</mark>"

    cfg = _cfg()
    collection_name = request.form.get("zotero_collection", "").strip()

    # Serialise Paper objects for the worker thread
    papers_data = [_paper_to_dict(p) for p in papers]
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
        return f"<mark>Zotero export failed: {job.error_message}</mark>"
    result = job.result
    if result["ok"]:
        return f'<ins>{result["msg"]}</ins>'
    return f'<mark>{result["msg"]}</mark>'


@bp.route("/zotero/paper/<path:uid>", methods=["POST"])
def zotero_export_paper(uid):
    uid = unquote(uid)
    paper = _cache().get_by_uid(uid)
    if paper is None:
        return "<mark>Paper not found.</mark>"

    cfg = _cfg()
    collection_name = request.form.get("zotero_collection", "").strip()
    papers_data = [_paper_to_dict(paper)]
    zot_job_id = _jobs().submit(_run_zotero_export, papers_data, cfg, collection_name)
    status_url = url_for("ui.zotero_export_status", job_id=zot_job_id)
    return (
        f'<div hx-get="{status_url}" hx-trigger="every 1s" hx-target="#zotero-status" hx-swap="innerHTML">'
        f'<span aria-busy="true">Sending to Zotero&hellip;</span></div>'
    )


def _paper_to_dict(paper: Paper) -> dict:
    """Serialise a Paper dataclass to a plain dict for thread-safe passing."""
    from dataclasses import asdict
    return asdict(paper)


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
        return '<article>Please select a .bib or .csv file.</article>'

    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in (".bib", ".csv"):
        return '<article>Unsupported file type. Use .bib or .csv.</article>'

    # Save to a temp file for processing
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = uploaded.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            return '<article>File too large (max 10 MB).</article>'
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from mosaic.bulk import read_dois
        dois = read_dois(tmp_path)
    except ValueError as e:
        return f'<article>{e}</article>'
    finally:
        tmp_path.unlink(missing_ok=True)

    if not dois:
        return '<article>No DOIs found in the uploaded file.</article>'

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
        return '<article>Job not found.</article>'

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
        return f'<article>Bulk download failed: {job.error_message}</article>'

    result = job.result
    html = f'<p><strong>Done:</strong> {result["ok"]} downloaded, {result["fail"]} failed.</p>'
    if result["results"]:
        html += '<table role="grid"><thead><tr><th>DOI</th><th>Status</th><th>File</th></tr></thead><tbody>'
        for r in result["results"]:
            icon = '<span class="badge-oa">&#10003;</span>' if r["status"] == "ok" else '<span class="badge-closed">&#10007;</span>'
            html += f'<tr><td>{r["doi"]}</td><td>{icon}</td><td>{r["path"]}</td></tr>'
        html += '</tbody></table>'
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
