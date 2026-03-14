"""PDF download logic with Unpaywall fallback."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from mosaic.db import Cache
from mosaic.models import Paper
from mosaic.sources import unpaywall

log = logging.getLogger(__name__)


def download(
    paper: Paper,
    download_dir: str,
    cache: Cache,
    unpaywall_email: str = "",
    filename_pattern: str = "{year}_{source}_{author}_{title}",
) -> str | None:
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
            log.debug("Direct PDF download failed for %s: %s", pdf_url, exc_info=True)

    # ── step 2: Unpaywall ─────────────────────────────────────────────────────
    if paper.doi and unpaywall_email:
        upw_url = unpaywall.resolve(paper.doi, unpaywall_email)
        if upw_url:
            try:
                _fetch(upw_url, str(dest))
                cache.set_download(paper.uid, str(dest), "ok")
                return str(dest)
            except Exception:
                log.debug("Unpaywall download failed for %s: %s", upw_url, exc_info=True)

    # ── step 3: browser session ───────────────────────────────────────────────
    landing_url = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else None)
    if landing_url:
        try:
            import asyncio

            from mosaic.auth import browser_download, find_session_for_url, list_sessions

            # Resolve HTTP redirects so domain matching works for known publisher
            # URLs. For doi.org → linkinghub → sciencedirect chains the final JS
            # redirect is only followable by a real browser, so when direct
            # matching still fails we fall back to trying every saved session —
            # the browser will follow the full chain including JS redirects.
            resolved_url = _resolve_redirect(landing_url)
            session = find_session_for_url(resolved_url)
            sessions_to_try = [session] if session else [s["name"] for s in list_sessions()]

            async def _try_sessions() -> bool:
                for s in sessions_to_try:
                    if await browser_download(resolved_url, str(dest), s):
                        return True
                return False

            if asyncio.run(_try_sessions()):
                cache.set_download(paper.uid, str(dest), "ok")
                return str(dest)
        except Exception:
            log.debug("Browser session download failed for %s", landing_url, exc_info=True)

    cache.set_download(paper.uid, "", "error: no pdf found")
    return None


def _resolve_redirect(url: str) -> str:
    """Follow HTTP redirects and return the final URL (e.g. doi.org → publisher)."""
    try:
        with httpx.Client(follow_redirects=True, timeout=10) as client:
            r = client.head(url)
            return str(r.url)
    except Exception:
        log.debug("Redirect resolution failed for %s", url, exc_info=True)
        return url


def _fetch(url: str, dest: str) -> None:
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(8192):
                f.write(chunk)
