"""Actions on a result set or paper: file exports, PDF downloads, Zotero, Obsidian."""

from __future__ import annotations

from urllib.parse import unquote

from flask import flash, redirect, request, url_for
from markupsafe import escape

from mosaic.models import Paper
from mosaic.ui.routes.common import (
    app_cache,
    app_cfg,
    bp,
    download_table,
    export_papers,
    form_flag,
    job_manager,
    job_papers,
    poll_html,
)
from mosaic.workflows import auto_index, download_papers

# ---------------------------------------------------------------------------
# Export and bulk actions on a result set
# ---------------------------------------------------------------------------


@bp.route("/export/<job_id>")
def export_results(job_id):
    papers = job_papers(job_id)
    if not papers:
        flash("Export results have expired. Please re-run your search.", "warning")
        return redirect(url_for("ui.search_page"))
    return export_papers(papers, request.args.get("format", "csv"), "mosaic_results")


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
    papers = job_papers(job_id)
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"
    dl_job_id = job_manager().submit(
        _run_download_all, [p.to_dict() for p in papers], app_cfg(), meta={"source_job": job_id}
    )
    status_url = url_for("ui.download_all_status", job_id=dl_job_id)
    return poll_html(
        status_url, "#download-all-status", f"Downloading {len(papers)} PDF(s)&hellip;"
    )


@bp.route("/download-all/status/<job_id>")
def download_all_status(job_id):
    jm = job_manager()
    job = jm.get(job_id)
    if job is None:
        return "<mark>Download job not found.</mark>"
    if job.status == "running":
        status_url = url_for("ui.download_all_status", job_id=job_id)
        return poll_html(status_url, "#download-all-status", "Downloading PDFs&hellip;")
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
    return html + download_table(report.items)


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
    return poll_html(status_url, "#zotero-status", "Sending to Zotero&hellip;", "1s", inline=True)


@bp.route("/zotero/export/<job_id>", methods=["POST"])
def zotero_export(job_id):
    papers = job_papers(job_id)
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"

    job = job_manager().get(job_id)
    pdf_map = dict(job.meta.get("pdf_map", {})) if job is not None else {}
    zot_job_id = job_manager().submit(
        _run_zotero_export,
        [p.to_dict() for p in papers],
        app_cfg(),
        request.form.get("zotero_collection", "").strip(),
        form_flag("zotero_local"),
        pdf_map,
    )
    return _zotero_poll(zot_job_id)


@bp.route("/zotero/export/status/<job_id>")
def zotero_export_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<mark>Zotero export job not found.</mark>"
    if job.status == "running":
        return _zotero_poll(job_id)
    job_manager().pop(job_id)
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
    paper = app_cache().get_by_uid(uid)
    if paper is None:
        return "<mark>Paper not found.</mark>"

    pdf_map = {}
    dl = app_cache().get_download(uid)
    if dl and dl["status"] == "ok" and dl["local_path"]:
        pdf_map[uid] = dl["local_path"]
    zot_job_id = job_manager().submit(
        _run_zotero_export,
        [paper.to_dict()],
        app_cfg(),
        request.form.get("zotero_collection", "").strip(),
        form_flag("zotero_local"),
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
    return poll_html(
        status_url, "#obsidian-status", "Exporting to Obsidian&hellip;", "1s", inline=True
    )


@bp.route("/obsidian/export/<job_id>", methods=["POST"])
def obsidian_export(job_id):
    papers = job_papers(job_id)
    if not papers:
        return "<mark>Export results have expired. Please re-run your search.</mark>"

    obs_job_id = job_manager().submit(
        _run_obsidian_export,
        [p.to_dict() for p in papers],
        app_cfg(),
        request.form.get("obsidian_folder", "").strip(),
    )
    return _obsidian_poll(obs_job_id)


@bp.route("/obsidian/paper/<path:uid>", methods=["POST"])
def obsidian_export_paper(uid):
    paper = app_cache().get_by_uid(unquote(uid))
    if paper is None:
        return "<mark>Paper not found.</mark>"
    obs_job_id = job_manager().submit(_run_obsidian_export, [paper.to_dict()], app_cfg())
    return _obsidian_poll(obs_job_id)


@bp.route("/obsidian/export/status/<job_id>")
def obsidian_export_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<mark>Obsidian export job not found.</mark>"
    if job.status == "running":
        return _obsidian_poll(job_id)
    job_manager().pop(job_id)
    if job.status == "error":
        return f"<mark>Obsidian export failed: {escape(job.error_message)}</mark>"
    result = job.result
    if result["ok"]:
        return f"<ins>{escape(result['msg'])}</ins>"
    return f"<mark>{escape(result['msg'])}</mark>"
