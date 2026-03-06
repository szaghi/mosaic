"""PDF download logic with Unpaywall fallback."""
from __future__ import annotations
from pathlib import Path
import httpx
from mosaic.models import Paper
from mosaic.sources import unpaywall
from mosaic.db import Cache


def download(paper: Paper, download_dir: str, cache: Cache, unpaywall_email: str = "") -> str | None:
    """
    Download PDF for a paper. Returns local path on success, None on failure.
    Tries: 1) known pdf_url  2) Unpaywall lookup by DOI
    """
    rec = cache.get_download(paper.uid)
    if rec and rec["status"] == "ok" and Path(rec["local_path"]).exists():
        return rec["local_path"]

    pdf_url = paper.pdf_url

    if not pdf_url and paper.doi and unpaywall_email:
        pdf_url = unpaywall.resolve(paper.doi, unpaywall_email)

    if not pdf_url:
        return None

    dest_dir = Path(download_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / paper.safe_filename()

    try:
        _fetch(pdf_url, str(dest))
        cache.set_download(paper.uid, str(dest), "ok")
        return str(dest)
    except Exception as e:
        cache.set_download(paper.uid, "", f"error: {e}")
        return None


def _fetch(url: str, dest: str) -> None:
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(8192):
                f.write(chunk)
