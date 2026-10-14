"""PDF download logic with Unpaywall fallback."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from mosaic.db import Cache
from mosaic.errors import DownloadError
from mosaic.models import Paper
from mosaic.pdf import HEADER_WINDOW, has_pdf_header, is_pdf_file
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
    Tries: 1) known pdf_url  2) every Unpaywall OA location  3) browser session
    """
    rec = cache.get_download(paper.uid)
    if rec and rec["status"] == "ok":
        if is_pdf_file(rec["local_path"]):
            return rec["local_path"]
        # Missing file, or an HTML page cached as "ok" by an older version: retry.
        log.info("Cached download for %s is missing or not a PDF; retrying", paper.uid)

    dest_dir = Path(download_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / paper.safe_filename(filename_pattern)

    # ── step 1: known pdf_url ─────────────────────────────────────────────────
    failure = "no pdf found"
    pdf_url = paper.pdf_url
    if pdf_url:
        try:
            _fetch(pdf_url, str(dest))
            cache.set_download(paper.uid, str(dest), "ok")
            return str(dest)
        except DownloadError as e:
            failure = str(e)
            log.debug("Direct PDF download rejected for %s: %s", pdf_url, e)
        except Exception:
            log.debug("Direct PDF download failed for %s", pdf_url, exc_info=True)

    # ── step 2: Unpaywall ─────────────────────────────────────────────────────
    # Try every OA location: publisher copies are often bot-walled while a
    # repository copy of the same paper downloads fine.
    if paper.doi and unpaywall_email:
        for upw_url in unpaywall.candidates(paper.doi, unpaywall_email):
            if upw_url == pdf_url:
                continue  # already tried in step 1
            try:
                _fetch(upw_url, str(dest))
                cache.set_download(paper.uid, str(dest), "ok")
                return str(dest)
            except DownloadError as e:
                failure = str(e)
                log.debug("Unpaywall download rejected for %s: %s", upw_url, e)
            except Exception:
                log.debug("Unpaywall download failed for %s", upw_url, exc_info=True)

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

    cache.set_download(paper.uid, "", f"error: {failure}")
    return None


# Elsevier DOIs resolve over HTTP only as far as linkinghub, whose page jumps to
# ScienceDirect via a delayed <meta refresh>. The PII in its path determines the
# ScienceDirect article URL, so map it directly instead of following the page.
_LINKINGHUB_PII = re.compile(r"^https?://linkinghub\.elsevier\.com/retrieve/pii/([A-Z0-9]+)", re.I)


def _publisher_landing(url: str) -> str:
    """Map known interstitial URLs to the publisher's article page."""
    m = _LINKINGHUB_PII.match(url)
    if m:
        return f"https://www.sciencedirect.com/science/article/pii/{m.group(1).upper()}"
    return url


def resolve_landing(url: str) -> str:
    """Follow HTTP redirects (e.g. doi.org -> publisher) and known interstitials.

    Returns the article page a browser would end up on, so domain matching
    against saved sessions works. Falls back to *url* on network errors.
    """
    try:
        with httpx.Client(follow_redirects=True, timeout=10) as client:
            url = str(client.head(url).url)
    except Exception:
        log.debug("Redirect resolution failed for %s", url, exc_info=True)
    return _publisher_landing(url)


# Backwards-compatible name used by callers and tests.
_resolve_redirect = resolve_landing


def _fetch(url: str, dest: str) -> None:
    """Stream *url* to *dest*, accepting only a PDF body.

    Publisher bot-checks and landing pages answer 200 with HTML, so the status
    code alone proves nothing. The body is written to a sibling ``.part`` file
    and renamed onto *dest* only once complete, so a failure never leaves a
    truncated or non-PDF file under the final name.

    Raises
    ------
    DownloadError
        If the body does not start with the PDF magic bytes.
    httpx.HTTPError
        On transport or HTTP status errors.
    """
    part = Path(dest).with_name(Path(dest).name + ".part")
    try:
        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            ctype = r.headers.get("content-type", "unknown").split(";")[0].strip()
            with open(part, "wb") as f:
                head = b""
                checked = False
                for chunk in r.iter_bytes(8192):
                    if checked:
                        f.write(chunk)
                        continue
                    # Buffer until the header window is filled: a chunk may be
                    # shorter than the magic itself.
                    head += chunk
                    if len(head) >= HEADER_WINDOW:
                        if not has_pdf_header(head):
                            raise DownloadError(f"not a pdf ({ctype})")
                        f.write(head)
                        checked = True
                if not checked:
                    if not has_pdf_header(head):
                        raise DownloadError(f"not a pdf ({ctype})")
                    f.write(head)
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
