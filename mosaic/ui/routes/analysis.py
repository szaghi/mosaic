"""Analysis pages: comparison tables and the citation network."""

from __future__ import annotations

import io

from flask import flash, redirect, render_template, request, send_file, url_for
from markupsafe import escape

from mosaic.services import select_cached_papers
from mosaic.ui.routes.common import (
    app_cfg,
    app_version,
    bp,
    file_response,
    form_flag,
    job_manager,
    poll_html,
    purge_stale_jobs,
    read_uploaded_dois,
    safe_int,
)

# ---------------------------------------------------------------------------
# Analysis — compare and citation network
# ---------------------------------------------------------------------------


@bp.route("/analysis")
def analysis_landing():
    return render_template("analysis.html", version=app_version())


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
        "compare.html", default_dims=", ".join(DEFAULT_DIMENSIONS), version=app_version()
    )


@bp.route("/compare", methods=["POST"])
def compare_submit():
    from mosaic.compare import DEFAULT_DIMENSIONS

    purge_stale_jobs()
    dois, error = read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    sort = request.form.get("sort", "")
    if sort not in ("", "citations", "year"):
        return "<article>Sort must be citations or year.</article>"
    raw_dims = request.form.get("dimensions", "")
    dims = [d.strip() for d in raw_dims.split(",") if d.strip()] or list(DEFAULT_DIMENSIONS)
    job_id = job_manager().submit(
        _run_compare,
        app_cfg(),
        request.form.get("query", "").strip(),
        dois,
        safe_int(request.form.get("n", 20), default=20, lo=1, hi=100),
        dims,
        sort,
    )
    status_url = url_for("ui.compare_status", job_id=job_id)
    return poll_html(status_url, "#compare-result", "Comparing papers&hellip;")


@bp.route("/compare/status/<job_id>")
def compare_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.compare_status", job_id=job_id)
        return poll_html(status_url, "#compare-result", "Comparing papers&hellip;")
    if job.status == "error":
        job_manager().pop(job_id)
        return f"<article><mark>Comparison failed: {escape(job.error_message)}</mark></article>"
    if not job.result["ok"]:
        job_manager().pop(job_id)
        return f"<article>{escape(job.result['msg'])}</article>"
    return render_template("partials/compare_table.html", job_id=job_id, **job.result)


@bp.route("/compare/export/<job_id>")
def compare_export(job_id):
    from mosaic.compare import format_csv, format_json_output, format_markdown

    job = job_manager().get(job_id)
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
    return render_template("network.html", version=app_version())


@bp.route("/network", methods=["POST"])
def network_submit():
    purge_stale_jobs()
    job_id = job_manager().submit(
        _run_network,
        app_cfg(),
        request.form.get("query", "").strip(),
        safe_int(request.form.get("depth", 2), default=2, lo=1, hi=5),
        safe_int(request.form.get("min_connections", 1), default=1, lo=0, hi=1000),
        form_flag("cluster"),
        meta={"top": safe_int(request.form.get("top", 10), default=10, lo=1, hi=200)},
    )
    status_url = url_for("ui.network_status", job_id=job_id)
    return poll_html(status_url, "#network-result", "Analysing the citation network&hellip;")


@bp.route("/network/status/<job_id>")
def network_status(job_id):
    from mosaic.network import count_edges

    job = job_manager().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.network_status", job_id=job_id)
        return poll_html(status_url, "#network-result", "Analysing the citation network&hellip;")
    if job.status == "error":
        job_manager().pop(job_id)
        return (
            f"<article><mark>Network analysis failed: {escape(job.error_message)}</mark></article>"
        )
    result = job.result
    if not result["ok"]:
        job_manager().pop(job_id)
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

    job = job_manager().get(job_id)
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
    return file_response(
        lambda path: export_graph(r["nodes"], r["adj"], r["papers"], path, r["clusters"]),
        f"mosaic_network{ext}",
        mimetype,
    )
