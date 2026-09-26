"""Library page — local cache management (``mosaic cache``)."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from markupsafe import escape

from mosaic.ui.routes.common import app_cache, app_version, bp, export_papers, safe_int

# ---------------------------------------------------------------------------
# Library (local cache management — `mosaic cache …`)
# ---------------------------------------------------------------------------

_LIBRARY_PAGE_SIZE = 50


@bp.route("/library")
def library_page():
    cache = app_cache()
    query = request.args.get("q", "").strip()
    page = safe_int(request.args.get("page", 1), default=1, lo=1, hi=100_000)
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
        version=app_version(),
    )


@bp.route("/library/export")
def library_export():
    query = request.args.get("q", "").strip()
    papers = app_cache().list_papers(limit=999_999, query=query)
    if not papers:
        flash("No papers to export.", "warning")
        return redirect(url_for("ui.library_page", q=query))
    return export_papers(papers, request.args.get("format", "csv"), "mosaic_library")


@bp.route("/library/verify", methods=["POST"])
def library_verify():
    results = app_cache().verify_downloads()
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
    removed = app_cache().clean_stubs()
    if removed:
        return f"<p>Removed {removed} stale download record(s).</p>"
    return "<p>Nothing to clean — all tracked files are present.</p>"


@bp.route("/library/clear", methods=["POST"])
def library_clear():
    if request.form.get("confirm") != "on":
        return "<p><mark>Tick the confirmation box to wipe the cache.</mark></p>"
    app_cache().clear()
    return "<p>Cache cleared.</p>"
