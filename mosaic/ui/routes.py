"""Flask route handlers for the MOSAIC web UI."""

from __future__ import annotations

import io
import json
import tempfile
import uuid
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from markupsafe import escape

from mosaic.models import Paper, SearchFilters
from mosaic.search import search_all
from mosaic.services import (
    FIELD_CHOICES,
    RAG_MODES,
    SORT_CHOICES,
    build_filters,
    format_answer,
    select_cached_papers,
    subset_uids,
)
from mosaic.source_registry import SHORTHAND_TO_CFG_KEY, build_sources, source_choices
from mosaic.workflows import auto_index, download_papers, finalize_search

bp = Blueprint("ui", __name__)


# Maximum upload size (10 MB, enforced manually)
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# format → (extension, mimetype) for paper-list downloads
_EXPORT_FORMATS: dict[str, tuple[str, str]] = {
    "csv": (".csv", "text/csv"),
    "json": (".json", "application/json"),
    "bib": (".bib", "application/x-bibtex"),
    "ris": (".ris", "application/x-research-info-systems"),
    "md": (".md", "text/markdown"),
    "markdown": (".markdown", "text/markdown"),
}


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
    """Drop finished jobs older than the retention window (and their data)."""
    _jobs()._cleanup()


def _version():
    from mosaic import __version__

    return __version__


def _safe_int(value, default: int = 10, lo: int = 1, hi: int = 200) -> int:
    """Parse an integer from form input, clamping to [lo, hi]."""
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def _flag(name: str) -> bool:
    return request.form.get(name) == "on"


def _build_filters(form) -> tuple[SearchFilters | None, str | None]:
    """Return (filters, optional_warning). Warning is set on invalid year format."""
    return build_filters(
        year=form.get("year", "").strip(),
        author=form.get("author", "").strip(),
        journal=form.get("journal", "").strip(),
        field=form.get("field", "all") or "all",
        raw_query=form.get("raw_query", "").strip(),
    )


def _poll(status_url: str, target: str, message: str, every: str = "2s", inline: bool = False):
    """HTML fragment that keeps polling *status_url* into *target*."""
    body = (
        f'<span aria-busy="true">{message}</span>'
        if inline
        else f'<article aria-busy="true">{message}</article>'
    )
    return (
        f'<div hx-get="{status_url}" hx-trigger="every {every}" hx-target="{target}"'
        f' hx-swap="innerHTML">{body}</div>'
    )


def _results(papers=(), errors=(), stats=None, job_id=None, **extra):
    return render_template(
        "partials/results.html",
        papers=list(papers),
        errors=[e for e in errors if e],
        stats=stats or {},
        job_id=job_id,
        version=_version(),
        **extra,
    )


def _job_papers(job_id: str) -> list[Paper] | None:
    """Papers produced by a finished search-like job, if it is still retained."""
    job = _jobs().get(job_id)
    if job is None or job.status != "done" or not isinstance(job.result, dict):
        return None
    return job.result.get("papers") or None


def _read_uploaded_dois(field: str = "file") -> tuple[list[str] | None, str | None]:
    """Parse DOIs from an uploaded .bib/.csv file → ``(dois | None, error | None)``."""
    uploaded = request.files.get(field)
    if not uploaded or not uploaded.filename:
        return None, None
    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in (".bib", ".csv"):
        return None, "Unsupported file type. Use .bib or .csv."
    content = uploaded.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        return None, "File too large (max 10 MB)."

    from mosaic.bulk import read_dois

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        return read_dois(tmp_path), None
    except ValueError as e:
        return None, str(e)
    finally:
        tmp_path.unlink(missing_ok=True)


def _file_response(write: Callable[[Path], None], filename: str, mimetype: str) -> Response:
    """Run *write(path)* in a temporary directory and send the result as a download."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / filename
        write(path)
        data = path.read_bytes()
    return send_file(
        io.BytesIO(data), mimetype=mimetype, as_attachment=True, download_name=filename
    )


def _export_papers(papers: list[Paper], fmt: str, basename: str):
    from mosaic.exporter import export

    if fmt not in _EXPORT_FORMATS:
        return f"Unsupported export format: {escape(fmt)}", 400
    ext, mimetype = _EXPORT_FORMATS[fmt]
    return _file_response(lambda path: export(papers, path), f"{basename}{ext}", mimetype)


def _download_table(items) -> str:
    """Render a DownloadReport's items as an HTML table."""
    html = '<table role="grid"><thead><tr><th>Paper</th><th>Status</th><th>File</th></tr></thead><tbody>'
    for item in items:
        if item.status == "ok":
            icon = '<span class="badge-oa">&#10003;</span>'
        elif item.status == "skip":
            icon = '<span class="badge-closed">&ndash;</span>'
        else:
            icon = '<span class="badge-closed">&#10007;</span>'
        label = item.paper.title if item.paper.title != item.paper.doi else item.paper.doi
        name = Path(item.path).name if item.path else ""
        html += f"<tr><td>{escape(label or '')}</td><td>{icon}</td><td>{escape(name)}</td></tr>"
    return html + "</tbody></table>"


@bp.app_template_filter("safe_url")
def _safe_url(value: str | None) -> str | None:
    """Only let http(s) links from third-party metadata into href attributes."""
    if value and urlsplit(value.strip()).scheme.lower() in ("http", "https"):
        return value
    return None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _source_list(cfg: dict) -> list[dict]:
    """Search-form source checkboxes, including custom sources."""
    src_cfg = cfg.get("sources", {})
    items = []
    for key, display_name in source_choices(cfg).items():
        cfg_key = SHORTHAND_TO_CFG_KEY.get(key)
        enabled = src_cfg.get(cfg_key, {}).get("enabled", True) if cfg_key else True
        items.append({"key": key, "name": display_name, "enabled": enabled})
    return items


def _run_search(sources, query, max_per_source, filters, progress, opts, history, cfg):
    """Executed in a worker thread: search, post-process, persist, auto-index."""
    from mosaic.db import Cache

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
    with Cache(cfg["db_path"]) as cache:
        papers = finalize_search(papers, cfg, cache, query=query, history=history, **opts)
        warning = auto_index(papers, cfg, cache)
        if warning:
            errors.append(warning)
        score_label = "Rel." if opts.get("sort_by") == "relevance" else None
        return {"papers": papers, "errors": errors, "stats": stats, "score_label": score_label}


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


@bp.route("/")
def search_page():
    cfg = _cfg()
    prefill_query = request.args.get("q", "")
    prefill_filters = {
        key: request.args.get(key, "")
        for key in ("year", "author", "journal", "field", "raw_query", "mode")
    }
    return render_template(
        "search.html",
        sources=_source_list(cfg),
        version=_version(),
        prefill_query=prefill_query,
        prefill_filters=prefill_filters,
    )


@bp.route("/search", methods=["POST"])
def search_submit():
    _purge_stale()
    cfg = _cfg()
    form = request.form
    query = form.get("query", "").strip()
    if not query:
        return _results(errors=["Please enter a search query."])

    field = form.get("field", "all") or "all"
    if field not in FIELD_CHOICES:
        return _results(errors=[f'Invalid field "{field}". Use: {", ".join(FIELD_CHOICES)}.'])
    sort_by = form.get("sort_by", "")
    if sort_by and sort_by not in SORT_CHOICES:
        return _results(errors=[f'Invalid sort "{sort_by}". Use: {", ".join(SORT_CHOICES)}.'])
    filters, year_warning = _build_filters(form)
    if year_warning:
        return _results(errors=[year_warning])

    # "cached" checkbox kept for backwards compatibility with older forms
    mode = form.get("mode") or ("cached" if _flag("cached") else "sources")
    max_results = _safe_int(form.get("max_results", 10))
    opts = {
        "oa_only": _flag("oa_only"),
        "pdf_only": _flag("pdf_only"),
        "sort_by": sort_by,
        "prefer_cache": _flag("prefer_cache"),
    }
    history_filters = {
        "year": form.get("year", ""),
        "author": form.get("author", ""),
        "journal": form.get("journal", ""),
        "field": field,
        "raw_query": form.get("raw_query", ""),
        "mode": mode,
    }

    if mode in ("cached", "semantic"):
        return _local_search(query, mode, max_results, filters, opts, history_filters)
    if mode != "sources":
        return _results(errors=[f'Unknown search mode "{mode}".'])

    choices = source_choices(cfg)
    selected = form.getlist("sources")
    all_sources = build_sources(cfg)
    if selected:
        selected_names = {choices[k] for k in selected if k in choices}
        sources = [s for s in all_sources if s.name in selected_names]
    elif form.get("_has_sources"):
        # User explicitly deselected all sources in the search form
        return _results(errors=["No sources selected. Please select at least one source."])
    else:
        sources = all_sources
    if not sources:
        return _results(
            errors=[
                "None of the selected sources is active (missing API key or disabled in Config)."
            ]
        )

    # Shared dict — written by _run_search worker, read by job_status polling
    progress: dict[str, str] = {s.name: "pending" for s in sources}
    history = {"filters": history_filters, "sources": sorted(progress)}
    jm = _jobs()
    job_id = jm.submit(
        _run_search,
        sources,
        query,
        max_results,
        filters,
        progress,
        opts,
        history,
        cfg,
        meta={"query": query, **opts},
    )
    job = jm.get(job_id)
    if job is not None:
        job.progress = progress

    return render_template(
        "partials/job_status.html",
        job_id=job_id,
        source_count=len(sources),
        status_url=url_for("ui.search_status", job_id=job_id),
        job_type="search",
        progress=progress,
    )


def _local_search(query, mode, max_results, filters, opts, history_filters):
    """Cache-only and semantic (vector index) searches — no network sources."""
    cfg, cache = _cfg(), _cache()
    downloaded_only = _flag("downloaded_only")
    sort_by = opts["sort_by"]
    if mode == "semantic":
        try:
            from mosaic.rag import semantic_search

            papers = semantic_search(
                query, cache, cfg, k=max_results, downloaded_only=downloaded_only
            )
        except Exception as e:
            return _results(errors=[f"Semantic search failed: {e}"])
        # BM25 relevance would clobber the similarity ordering
        if sort_by == "relevance":
            sort_by = ""
        score_label = "Sim."
    else:
        papers = cache.search_local(query)
        if downloaded_only:
            downloaded = cache.get_downloaded_uids()
            papers = [p for p in papers if p.uid in downloaded]
        score_label = "Rel." if sort_by == "relevance" else None

    if filters:
        papers = [p for p in papers if filters.match(p)]
    papers = finalize_search(
        papers,
        cfg,
        cache,
        query=query,
        oa_only=opts["oa_only"],
        pdf_only=opts["pdf_only"],
        sort_by=sort_by,
        save=False,
        history={"filters": history_filters, "sources": [mode]},
    )
    result = {"papers": papers, "errors": [], "stats": {}, "score_label": score_label}
    job_id = _jobs().register_done(result, meta={"query": query})
    return _results(papers, job_id=job_id, score_label=score_label)


@bp.route("/search/status/<job_id>")
def search_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return _results(errors=["Job not found."])

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
        return _results(errors=[job.error_message])

    # Done — the worker already filtered, sorted and saved the results; the
    # job is kept (until purged) so the export/Zotero/Obsidian actions work.
    result = job.result
    return _results(
        result["papers"],
        result["errors"],
        result["stats"],
        job_id=job_id,
        score_label=result.get("score_label"),
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


# ---------------------------------------------------------------------------
# Paper detail, download, citation
# ---------------------------------------------------------------------------


@bp.route("/paper/<path:uid>")
def paper_detail(uid):
    from mosaic.cite import SUPPORTED_STYLES

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
        "detail.html",
        paper=paper,
        download_status=download_status,
        cite_styles=SUPPORTED_STYLES,
        version=_version(),
        quote=quote,
    )


def _run_download(uid, cfg):
    """Executed in a worker thread."""
    from mosaic.db import Cache

    with Cache(cfg["db_path"]) as cache:
        paper = cache.get_by_uid(uid)
        if paper is None:
            return {"ok": False, "msg": "Paper not found."}

        report = download_papers([paper], cfg, cache, skip_without_link=False)
        item = report.items[0]
        if item.status != "ok":
            return {"ok": False, "msg": "Could not find a downloadable PDF."}
        msg = f"PDF saved: {Path(item.path).name}"
        warning = auto_index([paper], cfg, cache)
        if warning:
            msg += f" ({warning})"
        return {"ok": True, "msg": msg}


@bp.route("/download/<path:uid>", methods=["POST"])
def download_paper(uid):
    uid = unquote(uid)
    paper = _cache().get_by_uid(uid)
    if paper is None:
        return "<p>Paper not found.</p>", 404

    job_id = _jobs().submit(_run_download, uid, _cfg())
    status_url = url_for("ui.download_status", job_id=job_id)
    return _poll(status_url, "#download-status", "Downloading&hellip;", "1s", inline=True)


@bp.route("/download/status/<job_id>")
def download_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<mark>Download job not found.</mark>"

    if job.status == "running":
        status_url = url_for("ui.download_status", job_id=job_id)
        return _poll(status_url, "#download-status", "Downloading&hellip;", "1s", inline=True)

    _jobs().pop(job_id)
    if job.status == "error":
        return f"<mark>Download failed: {escape(job.error_message)}</mark>"

    result = job.result
    return f"<mark>{escape(result['msg'])}</mark>"


@bp.route("/cite/<path:uid>")
def cite_paper(uid):
    """Formatted citation for a cached paper (same styles as ``mosaic cite``)."""
    import httpx

    from mosaic.cite import SUPPORTED_STYLES, bibtex_citation, fetch_formatted_citation

    paper = _cache().get_by_uid(unquote(uid))
    if paper is None:
        return "<mark>Paper not found.</mark>"
    style = request.args.get("style", "bibtex").lower()
    if style not in SUPPORTED_STYLES:
        return f"<mark>Unknown style. Supported: {escape(', '.join(SUPPORTED_STYLES))}</mark>"

    if style == "bibtex":
        text = bibtex_citation(paper)
    else:
        if not paper.doi:
            return "<mark>This style is formatted by doi.org and needs a DOI.</mark>"
        email = _cfg().get("unpaywall", {}).get("email", "")
        try:
            text = fetch_formatted_citation(paper.doi, style, email)
        except httpx.HTTPStatusError as e:
            return f"<mark>HTTP error {e.response.status_code} fetching the citation.</mark>"
        except httpx.HTTPError:
            return "<mark>Network error — could not reach doi.org.</mark>"
    return (
        f'<pre id="citation-text" style="white-space:pre-wrap;">{escape(text)}</pre>'
        '<button type="button" class="outline secondary" style="padding:.2rem .6rem;font-size:.85em;"'
        " onclick=\"navigator.clipboard.writeText(document.getElementById('citation-text')"
        ".textContent);this.textContent='Copied';\">Copy</button>"
    )


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
        return _results(errors=["Please enter a DOI or arXiv ID."])
    sort_by = request.form.get("sort_by", "")
    if sort_by and sort_by not in SORT_CHOICES:
        return _results(errors=[f'Invalid sort "{sort_by}". Use: {", ".join(SORT_CHOICES)}.'])

    max_results = _safe_int(request.form.get("max_results", 10))
    cfg = _cfg()
    oa_email = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key = cfg.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")

    job_id = _jobs().submit(
        _run_similar,
        identifier,
        max_results,
        oa_email,
        ss_api_key,
        meta={
            "identifier": identifier,
            "oa_only": _flag("oa_only"),
            "pdf_only": _flag("pdf_only"),
            "sort_by": sort_by,
        },
    )

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
        return _results(errors=["Job not found."])

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
        return _results(errors=[job.error_message])

    result = job.result
    seed_title = result.get("seed_title")
    if seed_title is None:
        _jobs().pop(job_id)
        return _results(
            errors=[
                f"Paper not found: {job.meta.get('identifier', '')}. "
                "Check that the DOI or arXiv ID is correct."
            ]
        )

    # Post-process once; later polls (or re-renders) reuse the stored list
    if not result.get("processed"):
        meta = job.meta
        result["papers"] = finalize_search(
            result["papers"],
            _cfg(),
            _cache(),
            query=seed_title,
            oa_only=meta.get("oa_only", False),
            pdf_only=meta.get("pdf_only", False),
            sort_by=meta.get("sort_by", ""),
        )
        result["processed"] = True

    return _results(
        result["papers"],
        seed_title=seed_title,
        job_id=job_id,
        score_label="Rel." if job.meta.get("sort_by") == "relevance" else None,
    )


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
    return render_template("config.html", cfg=cfg, secrets=_secret_status(cfg), version=_version())


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
    old_db_path = _cfg().get("db_path")
    db_path = form.get("db_path", "").strip()
    if db_path:
        cfg["db_path"] = db_path

    cfg_mod.save(cfg)

    # Refresh app config (and the cache itself when the DB moved)
    current_app.config["MOSAIC_CFG"] = cfg
    if cfg.get("db_path") != old_db_path:
        from mosaic.db import Cache

        current_app.config["MOSAIC_CACHE"] = Cache(cfg["db_path"])

    if request.headers.get("HX-Request"):
        html = '<article style="padding:.5rem 1rem;"><ins>Configuration saved.</ins>'
        if warnings:
            html += "<ul>" + "".join(f"<li>{escape(w)}</li>" for w in warnings) + "</ul>"
        return html + "</article>"

    flash("Configuration saved.", "success")
    for w in warnings:
        flash(w, "warning")
    return redirect(url_for("ui.config_page"))


# ---------------------------------------------------------------------------
# Export and bulk actions on a result set
# ---------------------------------------------------------------------------


@bp.route("/export/<job_id>")
def export_results(job_id):
    papers = _job_papers(job_id)
    if not papers:
        flash("Export results have expired. Please re-run your search.", "warning")
        return redirect(url_for("ui.search_page"))
    return _export_papers(papers, request.args.get("format", "csv"), "mosaic_results")


def _run_download_all(papers_data, cfg):
    """Executed in a worker thread."""
    from mosaic.db import Cache

    with Cache(cfg["db_path"]) as cache:
        papers = [Paper.from_dict(d) for d in papers_data]
        report = download_papers(papers, cfg, cache)
        downloaded = [i.paper for i in report.items if i.status == "ok"]
        return {"report": report, "warning": auto_index(downloaded, cfg, cache)}


@bp.route("/download-all/<job_id>", methods=["POST"])
def download_all(job_id):
    papers = _job_papers(job_id)
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"
    dl_job_id = _jobs().submit(
        _run_download_all, [p.to_dict() for p in papers], _cfg(), meta={"source_job": job_id}
    )
    status_url = url_for("ui.download_all_status", job_id=dl_job_id)
    return _poll(status_url, "#download-all-status", f"Downloading {len(papers)} PDF(s)&hellip;")


@bp.route("/download-all/status/<job_id>")
def download_all_status(job_id):
    jm = _jobs()
    job = jm.get(job_id)
    if job is None:
        return "<mark>Download job not found.</mark>"
    if job.status == "running":
        status_url = url_for("ui.download_all_status", job_id=job_id)
        return _poll(status_url, "#download-all-status", "Downloading PDFs&hellip;")
    jm.pop(job_id)
    if job.status == "error":
        return f"<mark>Download failed: {escape(job.error_message)}</mark>"

    report = job.result["report"]
    # Let a later "Send to Zotero" on the same results attach these PDFs
    source = jm.get(job.meta.get("source_job", ""))
    if source is not None:
        source.meta.setdefault("pdf_map", {}).update(report.pdf_map)
    html = (
        f"<p><strong>Done:</strong> {report.count('ok')} downloaded, "
        f"{report.count('fail')} failed, {report.count('skip')} skipped (no PDF link).</p>"
    )
    if job.result.get("warning"):
        html += f"<p><mark>{escape(job.result['warning'])}</mark></p>"
    return html + _download_table(report.items)


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


def _run_zotero_export(papers_data, cfg, collection_name, force_local=False, pdf_map=None):
    """Executed in a worker thread."""
    from mosaic.workflows import push_to_zotero

    papers = [Paper.from_dict(d) for d in papers_data]
    return push_to_zotero(
        papers,
        cfg,
        collection_name=collection_name,
        force_local=force_local,
        pdf_map=pdf_map,
    )


def _zotero_poll(zot_job_id: str) -> str:
    status_url = url_for("ui.zotero_export_status", job_id=zot_job_id)
    return _poll(status_url, "#zotero-status", "Sending to Zotero&hellip;", "1s", inline=True)


@bp.route("/zotero/export/<job_id>", methods=["POST"])
def zotero_export(job_id):
    papers = _job_papers(job_id)
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"

    job = _jobs().get(job_id)
    pdf_map = dict(job.meta.get("pdf_map", {})) if job is not None else {}
    zot_job_id = _jobs().submit(
        _run_zotero_export,
        [p.to_dict() for p in papers],
        _cfg(),
        request.form.get("zotero_collection", "").strip(),
        _flag("zotero_local"),
        pdf_map,
    )
    return _zotero_poll(zot_job_id)


@bp.route("/zotero/export/status/<job_id>")
def zotero_export_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<mark>Zotero export job not found.</mark>"
    if job.status == "running":
        return _zotero_poll(job_id)
    _jobs().pop(job_id)
    if job.status == "error":
        return f"<mark>Zotero export failed: {escape(job.error_message)}</mark>"
    result = job.result
    msg = result["msg"]
    if result.get("attached"):
        msg += f" {result['attached']} PDF(s) linked."
    if result["ok"]:
        return f"<ins>{escape(msg)}</ins>"
    return f"<mark>{escape(msg)}</mark>"


@bp.route("/zotero/paper/<path:uid>", methods=["POST"])
def zotero_export_paper(uid):
    uid = unquote(uid)
    paper = _cache().get_by_uid(uid)
    if paper is None:
        return "<mark>Paper not found.</mark>"

    pdf_map = {}
    dl = _cache().get_download(uid)
    if dl and dl["status"] == "ok" and dl["local_path"]:
        pdf_map[uid] = dl["local_path"]
    zot_job_id = _jobs().submit(
        _run_zotero_export,
        [paper.to_dict()],
        _cfg(),
        request.form.get("zotero_collection", "").strip(),
        _flag("zotero_local"),
        pdf_map,
    )
    return _zotero_poll(zot_job_id)


# ---------------------------------------------------------------------------
# Obsidian export
# ---------------------------------------------------------------------------


def _run_obsidian_export(papers_data, cfg, subfolder=""):
    """Executed in a worker thread."""
    from mosaic.workflows import push_to_obsidian

    papers = [Paper.from_dict(d) for d in papers_data]
    return push_to_obsidian(papers, cfg, subfolder_override=subfolder)


def _obsidian_poll(obs_job_id: str) -> str:
    status_url = url_for("ui.obsidian_export_status", job_id=obs_job_id)
    return _poll(status_url, "#obsidian-status", "Exporting to Obsidian&hellip;", "1s", inline=True)


@bp.route("/obsidian/export/<job_id>", methods=["POST"])
def obsidian_export(job_id):
    papers = _job_papers(job_id)
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"

    obs_job_id = _jobs().submit(
        _run_obsidian_export,
        [p.to_dict() for p in papers],
        _cfg(),
        request.form.get("obsidian_folder", "").strip(),
    )
    return _obsidian_poll(obs_job_id)


@bp.route("/obsidian/paper/<path:uid>", methods=["POST"])
def obsidian_export_paper(uid):
    paper = _cache().get_by_uid(unquote(uid))
    if paper is None:
        return "<mark>Paper not found.</mark>"
    obs_job_id = _jobs().submit(_run_obsidian_export, [paper.to_dict()], _cfg())
    return _obsidian_poll(obs_job_id)


@bp.route("/obsidian/export/status/<job_id>")
def obsidian_export_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<mark>Obsidian export job not found.</mark>"
    if job.status == "running":
        return _obsidian_poll(job_id)
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


def _notebook_outcome(nb_result) -> dict:
    return {
        "ok": True,
        "nb_url": nb_result.url,
        "sources_added": nb_result.sources_added,
        "queued": nb_result.artifacts_queued,
        "warnings": nb_result.warnings(),
    }


def _run_notebook_from_query(name, query, max_results, filters, oa_only, pdf_only, artifacts, cfg):
    """Executed in a worker thread — search → download → create notebook."""
    import asyncio

    from mosaic.db import Cache
    from mosaic.notebooklm_bridge import _require_notebooklm, create_notebook, describe_error
    from mosaic.services import filter_papers

    _require_notebooklm()

    sources = build_sources(cfg)
    errors: list[str] = []
    papers = search_all(sources, query, max_per_source=max_results, filters=filters, errors=errors)
    papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only)

    if not papers:
        return {"ok": False, "msg": "No papers found for this query."}

    with Cache(cfg["db_path"]) as cache:
        report = download_papers(papers, cfg, cache, skip_without_link=False)
        papers_with_paths = [(i.paper, Path(i.path) if i.path else None) for i in report.items]

        try:
            nb_result = asyncio.run(create_notebook(name, papers_with_paths, artifacts=artifacts))
        except Exception as e:
            return {"ok": False, "msg": describe_error(e)}
        outcome = _notebook_outcome(nb_result)
        outcome.update(paper_count=len(papers), downloaded=report.count("ok"))
        return outcome


def _run_notebook_from_dir(name, from_dir, artifacts, cfg):
    """Executed in a worker thread — import PDFs from directory."""
    import asyncio

    from mosaic.notebooklm_bridge import (
        _require_notebooklm,
        create_notebook_from_dir,
        describe_error,
    )

    _require_notebooklm()

    directory = Path(from_dir).expanduser()
    if not directory.is_dir():
        return {"ok": False, "msg": f"Directory not found: {from_dir}"}

    try:
        nb_result = asyncio.run(create_notebook_from_dir(name, directory, artifacts=artifacts))
    except ValueError as e:
        return {"ok": False, "msg": str(e)}
    except Exception as e:
        return {"ok": False, "msg": describe_error(e)}
    return _notebook_outcome(nb_result)


@bp.route("/notebook")
def notebook_page():
    from mosaic.notebooklm_bridge import check_notebooklm_status

    nb_status = check_notebooklm_status()
    return render_template("notebook.html", version=_version(), nb_status=nb_status)


@bp.route("/notebook", methods=["POST"])
def notebook_submit():
    from mosaic.notebooklm_bridge import preflight_error

    _purge_stale()
    name = request.form.get("name", "").strip()
    if not name:
        return "<article>Please enter a notebook name.</article>"

    # Fail fast with remediation steps instead of a cryptic error later
    problem = preflight_error()
    if problem:
        return f"<article><mark>{escape(problem)}</mark></article>"

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
            return f"<article>{escape(year_warning)}</article>"
        job_id = _jobs().submit(
            _run_notebook_from_query,
            name,
            query,
            max_results,
            filters,
            _flag("oa_only"),
            _flag("pdf_only"),
            artifacts,
            cfg,
        )

    status_url = url_for("ui.notebook_status", job_id=job_id)
    return _poll(
        status_url,
        "#nb-results",
        f"Creating notebook <strong>{escape(name)}</strong>&hellip; (this may take a minute)",
    )


@bp.route("/notebook/status/<job_id>")
def notebook_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"

    if job.status == "running":
        status_url = url_for("ui.notebook_status", job_id=job_id)
        return _poll(
            status_url, "#nb-results", "Creating notebook&hellip; (this may take a minute)"
        )

    _jobs().pop(job_id)
    if job.status == "error":
        return (
            f"<article><mark>Notebook creation failed: {escape(job.error_message)}</mark></article>"
        )

    result = job.result
    if not result["ok"]:
        return f"<article><mark>{escape(result['msg'])}</mark></article>"

    lines = ["<ins>Notebook created successfully!</ins>"]
    if "paper_count" in result:
        lines.append(
            f"<p>{result['paper_count']} paper(s) found, {result['downloaded']} PDF(s) "
            f"downloaded, {result['sources_added']} source(s) added.</p>"
        )
    else:
        lines.append(f"<p>{result['sources_added']} source(s) added.</p>")
    if result["queued"]:
        lines.append(
            f"<p>{escape(', '.join(result['queued']))} queued &mdash; "
            "check NotebookLM in a few minutes.</p>"
        )
    for warning in result["warnings"]:
        lines.append(f"<p><mark>{escape(warning)}</mark></p>")
    lines.append(
        f'<p><a href="{escape(result["nb_url"])}" target="_blank" rel="noopener">'
        "Open in NotebookLM &rarr;</a></p>"
    )
    return "<article>" + "".join(lines) + "</article>"


# ---------------------------------------------------------------------------
# Bulk download
# ---------------------------------------------------------------------------


@bp.route("/bulk")
def bulk_page():
    return render_template("bulk.html", version=_version())


def _run_bulk_download(dois, cfg, opts):
    """Executed in a worker thread — same pipeline as ``mosaic get --from``."""
    from mosaic.db import Cache
    from mosaic.workflows import bulk_get, push_to_obsidian, push_to_zotero

    with Cache(cfg["db_path"]) as cache:
        papers, report = bulk_get(dois, cfg, cache)
        notes: list[str] = []
        if opts["zotero"]:
            res = push_to_zotero(
                papers,
                cfg,
                collection_name=opts["zotero_collection"],
                force_local=opts["zotero_local"],
                pdf_map=report.pdf_map,
            )
            notes.append(f"Zotero: {res['msg']}")
        if opts["obsidian"]:
            notes.append(f"Obsidian: {push_to_obsidian(papers, cfg)['msg']}")
        warning = auto_index(papers, cfg, cache)
        if warning:
            notes.append(warning)
        return {"report": report, "notes": notes}


@bp.route("/bulk", methods=["POST"])
def bulk_submit():
    _purge_stale()

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return "<article>Please select a .bib or .csv file.</article>"
    dois, error = _read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    if not dois:
        return "<article>No DOIs found in the uploaded file.</article>"

    opts = {
        "oa_only": _flag("oa_only"),
        "zotero": _flag("zotero"),
        "zotero_collection": request.form.get("zotero_collection", "").strip(),
        "zotero_local": _flag("zotero_local"),
        "obsidian": _flag("obsidian"),
    }
    job_id = _jobs().submit(
        _run_bulk_download, dois, _cfg(), opts, meta={"doi_count": len(dois), **opts}
    )
    status_url = url_for("ui.bulk_status", job_id=job_id)
    return _poll(status_url, "#results", f"Downloading {len(dois)} DOI(s)&hellip;")


@bp.route("/bulk/status/<job_id>")
def bulk_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"

    if job.status == "running":
        count = job.meta.get("doi_count", "?")
        status_url = url_for("ui.bulk_status", job_id=job_id)
        return _poll(status_url, "#results", f"Downloading {count} DOI(s)&hellip;")

    _jobs().pop(job_id)

    if job.status == "error":
        return f"<article>Bulk download failed: {escape(job.error_message)}</article>"

    report = job.result["report"]
    failed = report.count("fail")
    # --oa-only semantics: unresolvable papers are "skipped", not "failed"
    if job.meta.get("oa_only"):
        summary = f"{report.count('ok')} downloaded, {failed} skipped (no OA copy)."
    else:
        summary = f"{report.count('ok')} downloaded, {failed} failed."
    html = f"<p><strong>Done:</strong> {summary}</p>"
    for note in job.result["notes"]:
        html += f"<p>{escape(note)}</p>"
    if report.items:
        html += _download_table(report.items)
    return html


# ---------------------------------------------------------------------------
# Library (local cache management — `mosaic cache …`)
# ---------------------------------------------------------------------------

_LIBRARY_PAGE_SIZE = 50


@bp.route("/library")
def library_page():
    cache = _cache()
    query = request.args.get("q", "").strip()
    page = _safe_int(request.args.get("page", 1), default=1, lo=1, hi=100_000)
    total = cache.count_papers(query=query)
    papers = cache.list_papers(
        limit=_LIBRARY_PAGE_SIZE, offset=(page - 1) * _LIBRARY_PAGE_SIZE, query=query
    )
    pages = max(1, -(-total // _LIBRARY_PAGE_SIZE))
    return render_template(
        "library.html",
        stats=cache.stats(),
        papers=papers,
        query=query,
        page=page,
        pages=pages,
        total=total,
        offset=(page - 1) * _LIBRARY_PAGE_SIZE,
        version=_version(),
    )


@bp.route("/library/export")
def library_export():
    query = request.args.get("q", "").strip()
    papers = _cache().list_papers(limit=999_999, query=query)
    if not papers:
        flash("No papers to export.", "warning")
        return redirect(url_for("ui.library_page", q=query))
    return _export_papers(papers, request.args.get("format", "csv"), "mosaic_library")


@bp.route("/library/verify", methods=["POST"])
def library_verify():
    results = _cache().verify_downloads()
    if not results:
        return "<p>No completed downloads tracked.</p>"
    missing = [r for r in results if not r["exists"]]
    html = f"<p>{len(results) - len(missing)} file(s) OK, {len(missing)} missing.</p>"
    if missing:
        html += "<ul>" + "".join(
            f"<li><code>{escape(r['local_path'] or r['uid'])}</code></li>" for r in missing
        )
        html += "</ul><p><small>Use <em>Clean</em> to remove the stale records.</small></p>"
    return html


@bp.route("/library/clean", methods=["POST"])
def library_clean():
    removed = _cache().clean_stubs()
    if removed:
        return f"<p>Removed {removed} stale download record(s).</p>"
    return "<p>Nothing to clean — all tracked files are present.</p>"


@bp.route("/library/clear", methods=["POST"])
def library_clear():
    if request.form.get("confirm") != "on":
        return "<p><mark>Tick the confirmation box to wipe the cache.</mark></p>"
    _cache().clear()
    return "<p>Cache cleared.</p>"


# ---------------------------------------------------------------------------
# Analysis — compare and citation network
# ---------------------------------------------------------------------------


@bp.route("/analysis")
def analysis_landing():
    return render_template("analysis.html", version=_version())


def _run_compare(cfg, query, dois, n, dims, sort):
    """Executed in a worker thread — same selection as ``mosaic compare``."""
    from mosaic.compare import compare_papers
    from mosaic.db import Cache

    with Cache(cfg["db_path"]) as cache:
        papers = select_cached_papers(cache, query=query, dois=dois)
        if papers is None:
            papers = cache.get_all_papers()
        if not papers:
            return {"ok": False, "msg": "No matching papers in the cache. Run a search first."}
        if sort == "citations":
            papers = sorted(papers, key=lambda p: p.citation_count or 0, reverse=True)
        elif sort == "year":
            papers = sorted(papers, key=lambda p: p.year or 0, reverse=True)
        papers = papers[:n]
        errors: list[str] = []
        rows = compare_papers(papers, dims, cfg, errors=errors)
        llm_cfg = cfg.get("llm", {})
        return {
            "ok": True,
            "papers": papers,
            "rows": rows,
            "dims": dims,
            "errors": errors,
            "llm": bool(llm_cfg.get("api_key") and llm_cfg.get("provider")),
        }


@bp.route("/compare")
def compare_page():
    from mosaic.compare import DEFAULT_DIMENSIONS

    return render_template(
        "compare.html", default_dims=", ".join(DEFAULT_DIMENSIONS), version=_version()
    )


@bp.route("/compare", methods=["POST"])
def compare_submit():
    from mosaic.compare import DEFAULT_DIMENSIONS

    _purge_stale()
    dois, error = _read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    sort = request.form.get("sort", "")
    if sort not in ("", "citations", "year"):
        return "<article>Sort must be citations or year.</article>"
    raw_dims = request.form.get("dimensions", "")
    dims = [d.strip() for d in raw_dims.split(",") if d.strip()] or list(DEFAULT_DIMENSIONS)
    job_id = _jobs().submit(
        _run_compare,
        _cfg(),
        request.form.get("query", "").strip(),
        dois,
        _safe_int(request.form.get("n", 20), default=20, lo=1, hi=100),
        dims,
        sort,
    )
    status_url = url_for("ui.compare_status", job_id=job_id)
    return _poll(status_url, "#compare-result", "Comparing papers&hellip;")


@bp.route("/compare/status/<job_id>")
def compare_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.compare_status", job_id=job_id)
        return _poll(status_url, "#compare-result", "Comparing papers&hellip;")
    if job.status == "error":
        _jobs().pop(job_id)
        return f"<article><mark>Comparison failed: {escape(job.error_message)}</mark></article>"
    if not job.result["ok"]:
        _jobs().pop(job_id)
        return f"<article>{escape(job.result['msg'])}</article>"
    return render_template("partials/compare_table.html", job_id=job_id, **job.result)


@bp.route("/compare/export/<job_id>")
def compare_export(job_id):
    from mosaic.compare import format_csv, format_json_output, format_markdown

    job = _jobs().get(job_id)
    if job is None or job.status != "done" or not job.result.get("ok"):
        flash("Comparison results have expired. Please re-run it.", "warning")
        return redirect(url_for("ui.compare_page"))
    formatters = {
        "md": (format_markdown, ".md", "text/markdown"),
        "csv": (format_csv, ".csv", "text/csv"),
        "json": (format_json_output, ".json", "application/json"),
    }
    fmt = request.args.get("format", "md")
    if fmt not in formatters:
        return f"Unsupported export format: {escape(fmt)}", 400
    fn, ext, mimetype = formatters[fmt]
    content = fn(job.result["papers"], job.result["rows"], job.result["dims"])
    return send_file(
        io.BytesIO(content.encode("utf-8")),
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"mosaic_comparison{ext}",
    )


def _run_network(cfg, query, depth, min_connections, cluster):
    """Executed in a worker thread."""
    from mosaic.db import Cache
    from mosaic.services import analyse_network

    try:
        with Cache(cfg["db_path"]) as cache:
            graph = analyse_network(
                cache,
                query=query,
                depth=depth,
                min_connections=min_connections,
                cluster=cluster,
            )
    except LookupError as e:
        return {"ok": False, "msg": str(e)}
    return {"ok": True, **graph}


@bp.route("/network")
def network_page():
    return render_template("network.html", version=_version())


@bp.route("/network", methods=["POST"])
def network_submit():
    _purge_stale()
    job_id = _jobs().submit(
        _run_network,
        _cfg(),
        request.form.get("query", "").strip(),
        _safe_int(request.form.get("depth", 2), default=2, lo=1, hi=5),
        _safe_int(request.form.get("min_connections", 1), default=1, lo=0, hi=1000),
        _flag("cluster"),
        meta={"top": _safe_int(request.form.get("top", 10), default=10, lo=1, hi=200)},
    )
    status_url = url_for("ui.network_status", job_id=job_id)
    return _poll(status_url, "#network-result", "Analysing the citation network&hellip;")


@bp.route("/network/status/<job_id>")
def network_status(job_id):
    from mosaic.network import count_edges

    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.network_status", job_id=job_id)
        return _poll(status_url, "#network-result", "Analysing the citation network&hellip;")
    if job.status == "error":
        _jobs().pop(job_id)
        return (
            f"<article><mark>Network analysis failed: {escape(job.error_message)}</mark></article>"
        )
    result = job.result
    if not result["ok"]:
        _jobs().pop(job_id)
        return f"<article>{escape(result['msg'])}</article>"

    deg = result["deg"]

    def _ranked(uids):
        return sorted(uids, key=lambda uid: deg.get(uid, 0), reverse=True)

    groups = (
        [_ranked(c) for c in result["clusters"]]
        if result["clusters"]
        else [_ranked(result["nodes"])]
    )
    return render_template(
        "partials/network_report.html",
        job_id=job_id,
        groups=groups,
        clustered=bool(result["clusters"]),
        papers=result["papers"],
        deg=deg,
        top=job.meta.get("top", 10),
        n_nodes=len(result["nodes"]),
        n_edges=count_edges(result["nodes"], result["adj"]),
    )


@bp.route("/network/export/<job_id>")
def network_export(job_id):
    from mosaic.network import export_graph

    job = _jobs().get(job_id)
    if job is None or job.status != "done" or not job.result.get("ok"):
        flash("Network results have expired. Please re-run the analysis.", "warning")
        return redirect(url_for("ui.network_page"))
    formats = {
        "json": (".json", "application/json"),
        "gv": (".gv", "text/vnd.graphviz"),
        "md": (".md", "text/markdown"),
    }
    fmt = request.args.get("format", "json")
    if fmt not in formats:
        return f"Unsupported export format: {escape(fmt)}", 400
    ext, mimetype = formats[fmt]
    r = job.result
    return _file_response(
        lambda path: export_graph(r["nodes"], r["adj"], r["papers"], path, r["clusters"]),
        f"mosaic_network{ext}",
        mimetype,
    )


# ---------------------------------------------------------------------------
# RAG — Index, Ask, Chat
# ---------------------------------------------------------------------------

# In-process chat history: session_id → list of messages
# ({"role": "user"|"assistant", "content": str, "sources"?: [...], "error"?: bool}).
# Bounded so a long-running UI does not grow without limit.
_CHAT_MAX_SESSIONS = 50
_CHAT_MAX_MESSAGES = 60
_chat_histories: OrderedDict[str, list[dict]] = OrderedDict()


def _chat_history(sid: str) -> list[dict]:
    history = _chat_histories.setdefault(sid, [])
    _chat_histories.move_to_end(sid)
    while len(_chat_histories) > _CHAT_MAX_SESSIONS:
        _chat_histories.popitem(last=False)
    del history[:-_CHAT_MAX_MESSAGES]
    return history


def _chat_sid() -> str:
    session.permanent = True
    return session.setdefault("chat_id", str(uuid.uuid4()))


def _rag_index_status(cache):
    """Return dict with index stats (and problems to fix) for the template."""
    from mosaic.config import get_embedding_cfg
    from mosaic.rag import index_health

    cfg = _cfg()
    return {
        "total_papers": cache.count_papers(),
        "indexed_count": len(cache.get_indexed_uids()),
        # configured model vs. the one the existing index was built with
        "embedding_model": get_embedding_cfg(cfg).get("model", ""),
        "indexed_model": cache.get_rag_meta("embedding_model") or "",
        "health": index_health(cfg, cache),
    }


@bp.route("/rag")
def rag_landing():
    cache = _cache()
    info = _rag_index_status(cache)
    cfg = _cfg()
    llm_configured = bool(cfg.get("llm", {}).get("provider") and cfg.get("llm", {}).get("api_key"))
    return render_template(
        "rag_landing.html", version=_version(), llm_configured=llm_configured, **info
    )


@bp.route("/rag/index")
def rag_index_page():
    cache = _cache()
    info = _rag_index_status(cache)
    return render_template("rag_index.html", version=_version(), **info)


def _run_rag_index(cfg, reindex, batch_size, query="", dois=None, enrich=False):
    """Executed in a worker thread — same pipeline as ``mosaic index``."""
    from mosaic.db import Cache
    from mosaic.rag import index_health, index_papers

    with Cache(cfg["db_path"]) as cache:
        papers = select_cached_papers(cache, query=query, dois=dois)
        if papers is None:
            papers = cache.get_all_papers()
        if not papers:
            return {"newly": 0, "skipped": 0, "full_text": 0, "total": 0, "notes": []}

        notes: list[str] = []
        newly, skipped, full_text = index_papers(
            papers, cfg, cache, reindex=reindex, progress=False, batch_size=batch_size
        )
        if enrich or cfg.get("rag", {}).get("citations", {}).get("enabled", False):
            from mosaic.citations.enrichment import enrich_citations

            try:
                n_enriched, n_skipped = enrich_citations(papers, cfg, cache, reindex=reindex)
                notes.append(
                    f"Citation edges stored for {n_enriched} paper(s), {n_skipped} skipped."
                )
            except Exception as e:
                notes.append(f"Citation enrichment warning: {e}")
        notes.extend(index_health(cfg, cache))
        return {
            "newly": newly,
            "skipped": skipped,
            "full_text": full_text,
            "total": len(papers),
            "notes": notes,
        }


@bp.route("/rag/index", methods=["POST"])
def rag_index_submit():
    dois, error = _read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    batch_size = _safe_int(request.form.get("batch_size", 96), default=96, lo=1, hi=512)
    job_id = _jobs().submit(
        _run_rag_index,
        _cfg(),
        _flag("reindex"),
        batch_size,
        request.form.get("query", "").strip(),
        dois,
        _flag("enrich_citations"),
    )
    status_url = url_for("ui.rag_index_status", job_id=job_id)
    return _poll(status_url, "#index-job", "Indexing papers&hellip;")


@bp.route("/rag/index/status/<job_id>")
def rag_index_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.rag_index_status", job_id=job_id)
        return _poll(status_url, "#index-job", "Indexing papers&hellip;")
    _jobs().pop(job_id)
    if job.status == "error":
        return f"<article><mark>Indexing failed: {escape(job.error_message)}</mark></article>"
    r = job.result
    if not r["total"]:
        return "<article>No matching papers in the cache. Run some searches first.</article>"
    html = (
        f"<article><ins>Done.</ins> {r['newly']} paper(s) newly indexed "
        f"({r['full_text']} full-text, {r['newly'] - r['full_text']} metadata-only), "
        f"{r['skipped']} skipped (already indexed), {r['total']} selected."
    )
    for note in r["notes"]:
        html += f"<br><small>{escape(note)}</small>"
    return html + "</article>"


@bp.route("/rag/ask")
def rag_ask_page():
    return render_template("rag_ask.html", version=_version(), modes=RAG_MODES)


def _run_rag_ask(query, cfg, mode, top_k, subset_query, year, dois):
    """Executed in a worker thread — full RAG pipeline."""
    from mosaic.db import Cache
    from mosaic.rag import ask

    with Cache(cfg["db_path"]) as cache:
        pre_filter = subset_uids(cache, query=subset_query, dois=dois, year=year)
        answer, papers = ask(query, cfg, cache, mode=mode, k=top_k, pre_filter=pre_filter)
        return {"answer": answer, "papers": papers, "question": query, "mode": mode}


@bp.route("/rag/ask", methods=["POST"])
def rag_ask_submit():
    query = request.form.get("query", "").strip()
    if not query:
        return "<article>Please enter a question.</article>"

    mode = request.form.get("mode", "synthesis")
    if mode not in RAG_MODES:
        return f"<article>Unknown mode. Choose from: {', '.join(RAG_MODES)}.</article>"
    year = request.form.get("year", "").strip()
    if year:
        _, year_warning = build_filters(year=year)
        if year_warning:
            return f"<article>{escape(year_warning)}</article>"
    dois, error = _read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    top_k_raw = request.form.get("top_k", "").strip()
    top_k = _safe_int(top_k_raw, default=10, lo=1, hi=50) if top_k_raw else None

    job_id = _jobs().submit(
        _run_rag_ask,
        query,
        _cfg(),
        mode,
        top_k,
        request.form.get("subset_query", "").strip(),
        year,
        dois,
        meta={"show_sources": _flag("show_sources")},
    )
    status_url = url_for("ui.rag_ask_status", job_id=job_id)
    return _poll(status_url, "#ask-result", "Retrieving papers and generating answer&hellip;")


@bp.route("/rag/ask/status/<job_id>")
def rag_ask_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.rag_ask_status", job_id=job_id)
        return _poll(status_url, "#ask-result", "Retrieving papers and generating answer&hellip;")
    if job.status == "error":
        _jobs().pop(job_id)
        return f"<article><mark>Error: {escape(job.error_message)}</mark></article>"

    # Keep the job (until purged) so the answer can be downloaded
    result = job.result
    papers = result["papers"]
    html = f'<article><div class="rag-answer">{escape(result["answer"])}</div></article>'
    if papers:
        md_url = url_for("ui.rag_ask_export", job_id=job_id, format="md")
        json_url = url_for("ui.rag_ask_export", job_id=job_id, format="json")
        html += (
            f'<div class="export-bar"><strong>Save answer:</strong>'
            f'<a href="{md_url}" role="button" class="outline secondary">Markdown</a>'
            f'<a href="{json_url}" role="button" class="outline secondary">JSON</a></div>'
        )
    if job.meta.get("show_sources", True) and papers:
        html += '<details open><summary><strong>Source papers</strong></summary><ol class="source-list">'
        for p in papers:
            title = escape(p.title or "Untitled")
            authors = escape(", ".join(p.authors[:3]))
            year_str = escape(str(p.year or ""))
            detail_url = url_for("ui.paper_detail", uid=p.uid)
            html += f'<li><a href="{detail_url}">{title}</a> &mdash; {authors} ({year_str})</li>'
        html += "</ol></details>"
    return html


@bp.route("/rag/ask/export/<job_id>")
def rag_ask_export(job_id):
    job = _jobs().get(job_id)
    if job is None or job.status != "done":
        flash("This answer has expired. Please ask again.", "warning")
        return redirect(url_for("ui.rag_ask_page"))
    fmt = request.args.get("format", "md")
    if fmt not in ("md", "json"):
        return f"Unsupported export format: {escape(fmt)}", 400
    r = job.result
    content = format_answer(r["question"], r["mode"], r["answer"], r["papers"], fmt)
    return send_file(
        io.BytesIO(content.encode("utf-8")),
        mimetype="application/json" if fmt == "json" else "text/markdown",
        as_attachment=True,
        download_name=f"mosaic_answer.{fmt}",
    )


@bp.route("/rag/chat")
def rag_chat_page():
    history = _chat_history(_chat_sid())
    return render_template(
        "rag_chat.html",
        version=_version(),
        thread_html=_render_chat_thread(history),
        modes=RAG_MODES,
    )


def _run_rag_chat(query, history, cfg, mode, subset_query):
    """Executed in a worker thread — one conversational turn (with memory)."""
    from mosaic.db import Cache
    from mosaic.rag import chat_turn

    with Cache(cfg["db_path"]) as cache:
        pre_filter = subset_uids(cache, query=subset_query) if subset_query else None
        answer, papers = chat_turn(query, history, cfg, cache, mode=mode, pre_filter=pre_filter)
        sources = [{"title": p.title, "uid": p.uid, "year": p.year} for p in papers]
        return {"answer": answer, "sources": sources}


def _render_chat_thread(history, thinking: bool = False) -> str:
    """Return HTML for the chat thread content."""
    if not history and not thinking:
        return '<p class="stats-line"><em>No messages yet. Ask your first question below.</em></p>'
    parts = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "assistant"
        content = escape(msg["content"])
        if role == "user":
            parts.append(f'<div class="chat-msg chat-user">{content}</div>')
            continue
        body = f'<div class="chat-md">{content}</div>'
        sources = msg.get("sources") or []
        if sources:
            items = "".join(
                f'<li><a href="{url_for("ui.paper_detail", uid=s["uid"])}">'
                f"{escape(s['title'] or 'Untitled')}</a> ({escape(str(s['year'] or '?'))})</li>"
                for s in sources
            )
            body += (
                f'<details class="chat-sources"><summary>Sources ({len(sources)})</summary>'
                f"<ol>{items}</ol></details>"
            )
        css = "chat-msg chat-assistant" + (" chat-error" if msg.get("error") else "")
        parts.append(f'<div class="{css}">{body}</div>')
    if thinking:
        parts.append(
            '<div class="chat-msg chat-assistant" style="opacity:.6;">'
            '<span aria-busy="true">Thinking&hellip;</span></div>'
        )
    return "\n".join(parts)


def _oob_poll(status_url: str) -> str:
    """OOB swap that keeps the poll trigger alive outside #chat-thread."""
    return (
        f'<div id="chat-poll" hx-swap-oob="true">'
        f'<div hx-get="{status_url}" hx-trigger="every 2s"'
        f' hx-target="#chat-thread" hx-swap="innerHTML"></div>'
        f"</div>"
    )


def _oob_poll_stop() -> str:
    """OOB swap that clears #chat-poll, stopping the poll loop."""
    return '<div id="chat-poll" hx-swap-oob="true"></div>'


@bp.route("/rag/chat/send", methods=["POST"])
def rag_chat_send():
    query = request.form.get("query", "").strip()
    mode = request.form.get("mode", "synthesis")
    sid = _chat_sid()
    history = _chat_history(sid)

    if not query:
        return _render_chat_thread(history)
    if mode not in RAG_MODES:
        mode = "synthesis"

    # Prior turns sent to the LLM: plain role/content, failed turns excluded
    prior = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if not m.get("error") and m["role"] in ("user", "assistant")
    ]
    history.append({"role": "user", "content": query})
    job_id = _jobs().submit(
        _run_rag_chat,
        query,
        prior,
        _cfg(),
        mode,
        request.form.get("subset_query", "").strip(),
        meta={"sid": sid},
    )

    # Main swap → #chat-thread; OOB swap → #chat-poll (outside thread, survives swaps)
    status_url = url_for("ui.rag_chat_status", job_id=job_id)
    return _render_chat_thread(history, thinking=True) + "\n" + _oob_poll(status_url)


@bp.route("/rag/chat/status/<job_id>")
def rag_chat_status(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return _render_chat_thread(_chat_history(_chat_sid())) + "\n" + _oob_poll_stop()

    sid = job.meta.get("sid") or _chat_sid()
    history = _chat_history(sid)
    if job.status == "running":
        status_url = url_for("ui.rag_chat_status", job_id=job_id)
        return _render_chat_thread(history, thinking=True) + "\n" + _oob_poll(status_url)

    _jobs().pop(job_id)
    if job.status == "error":
        # Drop the unanswered question from the context sent on later turns
        if history and history[-1]["role"] == "user":
            history[-1]["error"] = True
        history.append(
            {"role": "assistant", "content": f"[Error: {job.error_message}]", "error": True}
        )
    else:
        answered = bool(job.result["sources"])
        if not answered and history and history[-1]["role"] == "user":
            # "No indexed papers…" replies carry no context worth replaying
            history[-1]["error"] = True
        history.append(
            {
                "role": "assistant",
                "content": job.result["answer"],
                "sources": job.result["sources"],
                "error": not answered,
            }
        )

    return _render_chat_thread(history) + "\n" + _oob_poll_stop()


@bp.route("/rag/chat/clear", methods=["POST"])
def rag_chat_clear():
    _chat_histories.pop(_chat_sid(), None)
    return '<p class="stats-line"><em>Conversation cleared.</em></p>' + "\n" + _oob_poll_stop()


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
