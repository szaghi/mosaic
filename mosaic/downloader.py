"""PDF download logic with Unpaywall fallback."""
from __future__ import annotations
from pathlib import Path
import httpx
from mosaic.models import Paper
from mosaic.sources import unpaywall
from mosaic.db import Cache


def download(paper: Paper, download_dir: str, cache: Cache, unpaywall_email: str = "",
             filename_pattern: str = "{year}_{source}_{author}_{title}") -> str | None:
    """
    Download PDF for a paper. Returns local path on success, None on failure.
    Tries: 1) known pdf_url  2) Unpaywall lookup by DOI  3) browser session
    """
    rec = cache.get_download(paper.uid)
    if rec and rec["status"] == "ok" and Path(rec["local_path"]).exists():
        return rec["local_path"]

    dest_dir = Path(download_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / paper.safe_filename(filename_pattern)

    # ── step 1: known pdf_url ─────────────────────────────────────────────────
    pdf_url = paper.pdf_url
    if pdf_url:
        try:
            _fetch(pdf_url, str(dest))
            cache.set_download(paper.uid, str(dest), "ok")
            return str(dest)
        except Exception:
            pass

    # ── step 2: Unpaywall ─────────────────────────────────────────────────────
    if paper.doi and unpaywall_email:
        upw_url = unpaywall.resolve(paper.doi, unpaywall_email)
        if upw_url:
            try:
                _fetch(upw_url, str(dest))
                cache.set_download(paper.uid, str(dest), "ok")
                return str(dest)
            except Exception:
                pass

    # ── step 3: browser session ───────────────────────────────────────────────
    landing_url = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else None)
    if landing_url:
        try:
            from mosaic.auth import find_session_for_url, browser_download
            import asyncio
            session = find_session_for_url(landing_url)
            if session:
                ok = asyncio.run(browser_download(landing_url, str(dest), session))
                if ok:
                    cache.set_download(paper.uid, str(dest), "ok")
                    return str(dest)
        except Exception:
            pass

    cache.set_download(paper.uid, "", "error: no pdf found")
    return None


def _fetch(url: str, dest: str) -> None:
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(8192):
                f.write(chunk)
