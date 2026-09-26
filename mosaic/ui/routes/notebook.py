"""Google NotebookLM notebook creation."""

from __future__ import annotations

from pathlib import Path

from flask import render_template, request, url_for
from markupsafe import escape

from mosaic.search import search_all
from mosaic.source_registry import build_sources
from mosaic.ui.routes.common import (
    app_cfg,
    app_version,
    bp,
    form_filters,
    form_flag,
    job_manager,
    poll_html,
    purge_stale_jobs,
    safe_int,
)
from mosaic.workflows import download_papers

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
    from mosaic.notebooklm_bridge import create_notebook, describe_error, require_notebooklm
    from mosaic.services import filter_papers

    require_notebooklm()

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
        create_notebook_from_dir,
        describe_error,
        require_notebooklm,
    )

    require_notebooklm()

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
    return render_template("notebook.html", version=app_version(), nb_status=nb_status)


@bp.route("/notebook", methods=["POST"])
def notebook_submit():
    from mosaic.notebooklm_bridge import preflight_error

    purge_stale_jobs()
    name = request.form.get("name", "").strip()
    if not name:
        return "<article>Please enter a notebook name.</article>"

    # Fail fast with remediation steps instead of a cryptic error later
    problem = preflight_error()
    if problem:
        return f"<article><mark>{escape(problem)}</mark></article>"

    input_mode = request.form.get("input_mode", "query")
    artifacts: set[str] = set(request.form.getlist("artifacts"))
    cfg = app_cfg()

    if input_mode == "dir":
        from_dir = request.form.get("from_dir", "").strip()
        if not from_dir:
            return "<article>Please enter a PDF directory path.</article>"
        job_id = job_manager().submit(_run_notebook_from_dir, name, from_dir, artifacts, cfg)
    else:
        query = request.form.get("query", "").strip()
        if not query:
            return "<article>Please enter a search query.</article>"
        max_results = safe_int(request.form.get("max_results", 10))
        filters, year_warning = form_filters(request.form)
        if year_warning:
            return f"<article>{escape(year_warning)}</article>"
        job_id = job_manager().submit(
            _run_notebook_from_query,
            name,
            query,
            max_results,
            filters,
            form_flag("oa_only"),
            form_flag("pdf_only"),
            artifacts,
            cfg,
        )

    status_url = url_for("ui.notebook_status", job_id=job_id)
    return poll_html(
        status_url,
        "#nb-results",
        f"Creating notebook <strong>{escape(name)}</strong>&hellip; (this may take a minute)",
    )


@bp.route("/notebook/status/<job_id>")
def notebook_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"

    if job.status == "running":
        status_url = url_for("ui.notebook_status", job_id=job_id)
        return poll_html(
            status_url, "#nb-results", "Creating notebook&hellip; (this may take a minute)"
        )

    job_manager().pop(job_id)
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
