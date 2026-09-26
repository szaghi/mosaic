"""Blueprint and helpers shared by every web UI route module."""

from __future__ import annotations

import io
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, Response, current_app, render_template, request, send_file
from markupsafe import escape

from mosaic.models import Paper, SearchFilters
from mosaic.services import build_filters

bp = Blueprint("ui", __name__)


# Maximum upload size (10 MB, enforced manually)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# format → (extension, mimetype) for paper-list downloads
EXPORT_FORMATS: dict[str, tuple[str, str]] = {
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


def app_cfg():
    return current_app.config["MOSAIC_CFG"]


def app_cache():
    return current_app.config["MOSAIC_CACHE"]


def job_manager():
    return current_app.config["JOB_MANAGER"]


def purge_stale_jobs():
    """Drop finished jobs older than the retention window (and their data)."""
    job_manager().purge_stale()


def app_version():
    from mosaic import __version__

    return __version__


def safe_int(value, default: int = 10, lo: int = 1, hi: int = 200) -> int:
    """Parse an integer from form input, clamping to [lo, hi]."""
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def form_flag(name: str) -> bool:
    return request.form.get(name) == "on"


def form_filters(form) -> tuple[SearchFilters | None, str | None]:
    """Return (filters, optional_warning). Warning is set on invalid year format."""
    return build_filters(
        year=form.get("year", "").strip(),
        author=form.get("author", "").strip(),
        journal=form.get("journal", "").strip(),
        field=form.get("field", "all") or "all",
        raw_query=form.get("raw_query", "").strip(),
    )


def poll_html(status_url: str, target: str, message: str, every: str = "2s", inline: bool = False):
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


def render_results(papers=(), errors=(), stats=None, job_id=None, **extra):
    return render_template(
        "partials/results.html",
        papers=list(papers),
        errors=[e for e in errors if e],
        stats=stats or {},
        job_id=job_id,
        version=app_version(),
        **extra,
    )


def job_papers(job_id: str) -> list[Paper] | None:
    """Papers produced by a finished search-like job, if it is still retained."""
    job = job_manager().get(job_id)
    if job is None or job.status != "done" or not isinstance(job.result, dict):
        return None
    return job.result.get("papers") or None


def read_uploaded_dois(field: str = "file") -> tuple[list[str] | None, str | None]:
    """Parse DOIs from an uploaded .bib/.csv file → ``(dois | None, error | None)``."""
    uploaded = request.files.get(field)
    if not uploaded or not uploaded.filename:
        return None, None
    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in (".bib", ".csv"):
        return None, "Unsupported file type. Use .bib or .csv."
    content = uploaded.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
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


def file_response(write: Callable[[Path], None], filename: str, mimetype: str) -> Response:
    """Run *write(path)* in a temporary directory and send the result as a download."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / filename
        write(path)
        data = path.read_bytes()
    return send_file(
        io.BytesIO(data), mimetype=mimetype, as_attachment=True, download_name=filename
    )


def export_papers(papers: list[Paper], fmt: str, basename: str):
    from mosaic.exporter import export

    if fmt not in EXPORT_FORMATS:
        return f"Unsupported export format: {escape(fmt)}", 400
    ext, mimetype = EXPORT_FORMATS[fmt]
    return file_response(lambda path: export(papers, path), f"{basename}{ext}", mimetype)


def download_table(items) -> str:
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
def safe_url(value: str | None) -> str | None:
    """Only let http(s) links from third-party metadata into href attributes."""
    if value and urlsplit(value.strip()).scheme.lower() in ("http", "https"):
        return value
    return None
