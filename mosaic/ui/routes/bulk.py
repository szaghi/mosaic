"""Bulk PDF download from a .bib / .csv file (``mosaic get --from``)."""

from __future__ import annotations

from flask import render_template, request, url_for
from markupsafe import escape

from mosaic.ui.routes.common import (
    app_cfg,
    app_version,
    bp,
    download_table,
    form_flag,
    job_manager,
    poll_html,
    purge_stale_jobs,
    read_uploaded_dois,
)
from mosaic.workflows import auto_index

# ---------------------------------------------------------------------------
# Bulk download
# ---------------------------------------------------------------------------


@bp.route("/bulk")
def bulk_page():
    return render_template("bulk.html", version=app_version())


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
    purge_stale_jobs()

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return "<article>Please select a .bib or .csv file.</article>"
    dois, error = read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    if not dois:
        return "<article>No DOIs found in the uploaded file.</article>"

    opts = {
        "oa_only": form_flag("oa_only"),
        "zotero": form_flag("zotero"),
        "zotero_collection": request.form.get("zotero_collection", "").strip(),
        "zotero_local": form_flag("zotero_local"),
        "obsidian": form_flag("obsidian"),
    }
    job_id = job_manager().submit(
        _run_bulk_download, dois, app_cfg(), opts, meta={"doi_count": len(dois), **opts}
    )
    status_url = url_for("ui.bulk_status", job_id=job_id)
    return poll_html(status_url, "#results", f"Downloading {len(dois)} DOI(s)&hellip;")


@bp.route("/bulk/status/<job_id>")
def bulk_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"

    if job.status == "running":
        count = job.meta.get("doi_count", "?")
        status_url = url_for("ui.bulk_status", job_id=job_id)
        return poll_html(status_url, "#results", f"Downloading {count} DOI(s)&hellip;")

    job_manager().pop(job_id)

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
        html += download_table(report.items)
    return html
