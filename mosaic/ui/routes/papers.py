"""Paper detail page: single-paper download and citations."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote

from flask import flash, redirect, render_template, request, url_for
from markupsafe import escape

from mosaic.ui.routes.common import app_cache, app_cfg, app_version, bp, job_manager, poll_html
from mosaic.workflows import auto_index, download_papers

# ---------------------------------------------------------------------------
# Paper detail, download, citation
# ---------------------------------------------------------------------------


@bp.route("/paper/<path:uid>")
def paper_detail(uid):
    from mosaic.cite import SUPPORTED_STYLES

    uid = unquote(uid)
    paper = app_cache().get_by_uid(uid)
    if paper is None:
        flash("Paper not found in cache.", "warning")
        return redirect(url_for("ui.search_page"))

    dl = app_cache().get_download(uid)
    download_status = None
    if dl:
        download_status = {"path": dl["local_path"], "status": dl["status"]}

    return render_template(
        "detail.html",
        paper=paper,
        download_status=download_status,
        cite_styles=SUPPORTED_STYLES,
        version=app_version(),
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
    paper = app_cache().get_by_uid(uid)
    if paper is None:
        return "<p>Paper not found.</p>", 404

    job_id = job_manager().submit(_run_download, uid, app_cfg())
    status_url = url_for("ui.download_status", job_id=job_id)
    return poll_html(status_url, "#download-status", "Downloading&hellip;", "1s", inline=True)


@bp.route("/download/status/<job_id>")
def download_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<mark>Download job not found.</mark>"

    if job.status == "running":
        status_url = url_for("ui.download_status", job_id=job_id)
        return poll_html(status_url, "#download-status", "Downloading&hellip;", "1s", inline=True)

    job_manager().pop(job_id)
    if job.status == "error":
        return f"<mark>Download failed: {escape(job.error_message)}</mark>"

    result = job.result
    return f"<mark>{escape(result['msg'])}</mark>"


@bp.route("/cite/<path:uid>")
def cite_paper(uid):
    """Formatted citation for a cached paper (same styles as ``mosaic cite``)."""
    import httpx

    from mosaic.cite import SUPPORTED_STYLES, bibtex_citation, fetch_formatted_citation

    paper = app_cache().get_by_uid(unquote(uid))
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
        email = app_cfg().get("unpaywall", {}).get("email", "")
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
