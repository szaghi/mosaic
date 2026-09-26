"""Search, similar-paper and history pages."""

from __future__ import annotations

import json

from flask import Response, render_template, request, stream_with_context, url_for

from mosaic.search import search_all
from mosaic.services import FIELD_CHOICES, SORT_CHOICES
from mosaic.source_registry import SHORTHAND_TO_CFG_KEY, build_sources, source_choices
from mosaic.ui.routes.common import (
    app_cache,
    app_cfg,
    app_version,
    bp,
    form_filters,
    form_flag,
    job_manager,
    purge_stale_jobs,
    render_results,
    safe_int,
)
from mosaic.workflows import auto_index, finalize_search

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
    cfg = app_cfg()
    prefill_query = request.args.get("q", "")
    prefill_filters = {
        key: request.args.get(key, "")
        for key in ("year", "author", "journal", "field", "raw_query", "mode")
    }
    return render_template(
        "search.html",
        sources=_source_list(cfg),
        version=app_version(),
        prefill_query=prefill_query,
        prefill_filters=prefill_filters,
    )


@bp.route("/search", methods=["POST"])
def search_submit():
    purge_stale_jobs()
    cfg = app_cfg()
    form = request.form
    query = form.get("query", "").strip()
    if not query:
        return render_results(errors=["Please enter a search query."])

    field = form.get("field", "all") or "all"
    if field not in FIELD_CHOICES:
        return render_results(errors=[f'Invalid field "{field}". Use: {", ".join(FIELD_CHOICES)}.'])
    sort_by = form.get("sort_by", "")
    if sort_by and sort_by not in SORT_CHOICES:
        return render_results(errors=[f'Invalid sort "{sort_by}". Use: {", ".join(SORT_CHOICES)}.'])
    filters, year_warning = form_filters(form)
    if year_warning:
        return render_results(errors=[year_warning])

    # "cached" checkbox kept for backwards compatibility with older forms
    mode = form.get("mode") or ("cached" if form_flag("cached") else "sources")
    max_results = safe_int(form.get("max_results", 10))
    opts = {
        "oa_only": form_flag("oa_only"),
        "pdf_only": form_flag("pdf_only"),
        "sort_by": sort_by,
        "prefer_cache": form_flag("prefer_cache"),
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
        return render_results(errors=[f'Unknown search mode "{mode}".'])

    choices = source_choices(cfg)
    selected = form.getlist("sources")
    all_sources = build_sources(cfg)
    if selected:
        selected_names = {choices[k] for k in selected if k in choices}
        sources = [s for s in all_sources if s.name in selected_names]
    elif form.get("_has_sources"):
        # User explicitly deselected all sources in the search form
        return render_results(errors=["No sources selected. Please select at least one source."])
    else:
        sources = all_sources
    if not sources:
        return render_results(
            errors=[
                "None of the selected sources is active (missing API key or disabled in Config)."
            ]
        )

    # Shared dict — written by _run_search worker, read by job_status polling
    progress: dict[str, str] = {s.name: "pending" for s in sources}
    history = {"filters": history_filters, "sources": sorted(progress)}
    jm = job_manager()
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
    cfg, cache = app_cfg(), app_cache()
    downloaded_only = form_flag("downloaded_only")
    sort_by = opts["sort_by"]
    if mode == "semantic":
        try:
            from mosaic.rag import semantic_search

            papers = semantic_search(
                query, cache, cfg, k=max_results, downloaded_only=downloaded_only
            )
        except Exception as e:
            return render_results(errors=[f"Semantic search failed: {e}"])
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
    job_id = job_manager().register_done(result, meta={"query": query})
    return render_results(papers, job_id=job_id, score_label=score_label)


@bp.route("/search/status/<job_id>")
def search_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return render_results(errors=["Job not found."])

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
        job_manager().pop(job_id)
        return render_results(errors=[job.error_message])

    # Done — the worker already filtered, sorted and saved the results; the
    # job is kept (until purged) so the export/Zotero/Obsidian actions work.
    result = job.result
    return render_results(
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
        job = job_manager().get(job_id)
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
# Similar
# ---------------------------------------------------------------------------


@bp.route("/similar")
def similar_page():
    identifier = request.args.get("identifier", "")
    return render_template("similar.html", identifier=identifier, version=app_version())


@bp.route("/similar", methods=["POST"])
def similar_submit():
    purge_stale_jobs()
    identifier = request.form.get("identifier", "").strip()
    if not identifier:
        return render_results(errors=["Please enter a DOI or arXiv ID."])
    sort_by = request.form.get("sort_by", "")
    if sort_by and sort_by not in SORT_CHOICES:
        return render_results(errors=[f'Invalid sort "{sort_by}". Use: {", ".join(SORT_CHOICES)}.'])

    max_results = safe_int(request.form.get("max_results", 10))
    cfg = app_cfg()
    oa_email = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key = cfg.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")

    job_id = job_manager().submit(
        _run_similar,
        identifier,
        max_results,
        oa_email,
        ss_api_key,
        meta={
            "identifier": identifier,
            "oa_only": form_flag("oa_only"),
            "pdf_only": form_flag("pdf_only"),
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
    job = job_manager().get(job_id)
    if job is None:
        return render_results(errors=["Job not found."])

    if job.status == "running":
        return render_template(
            "partials/job_status.html",
            job_id=job_id,
            source_count=2,
            status_url=url_for("ui.similar_status", job_id=job_id),
            job_type="similar",
        )

    if job.status == "error":
        job_manager().pop(job_id)
        return render_results(errors=[job.error_message])

    result = job.result
    seed_title = result.get("seed_title")
    if seed_title is None:
        job_manager().pop(job_id)
        return render_results(
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
            app_cfg(),
            app_cache(),
            query=seed_title,
            oa_only=meta.get("oa_only", False),
            pdf_only=meta.get("pdf_only", False),
            sort_by=meta.get("sort_by", ""),
        )
        result["processed"] = True

    return render_results(
        result["papers"],
        seed_title=seed_title,
        job_id=job_id,
        score_label="Rel." if job.meta.get("sort_by") == "relevance" else None,
    )


@bp.route("/history")
def history_page():
    searches = app_cache().list_searches(limit=50)
    for s in searches:
        try:
            s["filters"] = json.loads(s.get("filters_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            s["filters"] = {}
    return render_template("history.html", searches=searches, version=app_version())
