"""Browser session management for authenticated PDF access."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

log = logging.getLogger(__name__)

_SESSIONS_DIR = Path.home() / ".config" / "mosaic" / "sessions"

# PDF link heuristics — tried in order
_PDF_SELECTORS = [
    "a[href$='.pdf']",
    "a[href*='.pdf?']",
    "a[href*='/pdf/']",
    "a[href*='download=pdf']",
    "a[href*='type=printable']",
]
_PDF_TEXT_PATTERNS = [
    "download pdf",
    "get pdf",
    "view pdf",
    "full text pdf",
    "pdf download",
    "download full text",
]


# ── session path helpers ──────────────────────────────────────────────────────


def session_path(name: str) -> Path:
    return _SESSIONS_DIR / f"{name}.json"


def _meta_path(name: str) -> Path:
    return _SESSIONS_DIR / f"{name}.meta.json"


def _save_meta(name: str, login_url: str) -> None:
    meta = {"login_url": login_url, "domain": urlparse(login_url).netloc}
    # 0o600: meta file lives alongside session cookies — restrict to owner only
    raw_fd = os.open(str(_meta_path(name)), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(raw_fd, "w") as f:
        json.dump(meta, f)


def _load_meta(name: str) -> dict:
    path = _meta_path(name)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def session_is_valid(name: str) -> bool:
    """Return True if the saved session has at least one non-expired cookie.

    Session cookies (expires == -1) cannot be validated from the file alone
    and are assumed still present. The check only fails when every timed
    cookie in the file has passed its expiry timestamp.
    """
    path = session_path(name)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        now = time.time()
        timed = [c for c in data.get("cookies", []) if c.get("expires", -1) > 0]
        if not timed:
            # Only session cookies — cannot determine validity from file
            return True
        return any(c["expires"] > now for c in timed)
    except Exception:
        log.debug("Could not parse session file %s", path, exc_info=True)
        return True  # Assume valid if file can't be parsed


# ── session listing / deletion ────────────────────────────────────────────────


def list_sessions() -> list[dict]:
    """Return metadata for all saved sessions."""
    if not _SESSIONS_DIR.exists():
        return []
    sessions = []
    for f in sorted(_SESSIONS_DIR.glob("*.json")):
        if f.stem.endswith(".meta"):
            continue
        stat = f.stat()
        meta = _load_meta(f.stem)
        sessions.append(
            {
                "name": f.stem,
                "saved": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "domain": meta.get("domain", "—"),
                "valid": session_is_valid(f.stem),
                "path": str(f),
            }
        )
    return sessions


def delete_session(name: str) -> bool:
    """Remove a saved session and its metadata. Returns True if it existed."""
    path = session_path(name)
    if path.exists():
        path.unlink()
        meta = _meta_path(name)
        if meta.exists():
            meta.unlink()
        return True
    return False


def find_session_for_url(url: str) -> str | None:
    """Return the session name whose domain best matches the given URL, or None."""
    if not url or not _SESSIONS_DIR.exists():
        return None
    paper_domain = urlparse(url).netloc.lower()
    for f in sorted(_SESSIONS_DIR.glob("*.json")):
        if f.stem.endswith(".meta"):
            continue
        meta = _load_meta(f.stem)
        session_domain = meta.get("domain", "").lower()
        if session_domain and (session_domain in paper_domain or paper_domain in session_domain):
            return f.stem
    return None


# ── browser helpers ───────────────────────────────────────────────────────────

# Firefox is preferred for both headed and headless operations: its TLS
# fingerprint passes Cloudflare Bot Management where headless Chromium is
# blocked, and using the same browser for login and headless reuse ensures
# the cf_clearance cookie (which is fingerprint-bound) remains valid.
_BROWSER_PREFERENCE = ("firefox", "chromium", "webkit")
_HEADLESS_PREFERENCE = ("firefox", "chromium", "webkit")


async def _launch_browser(p, *, headless: bool = False):
    """Try browsers in order and return the first one that launches successfully."""
    from rich import print as rprint

    order = _HEADLESS_PREFERENCE if headless else _BROWSER_PREFERENCE
    for name in order:
        try:
            browser = await getattr(p, name).launch(headless=headless)
            if not headless:
                rprint(f"[dim]Using {name}[/dim]")
            return browser
        except Exception:
            log.debug("Failed to launch %s (headless=%s)", name, headless, exc_info=True)
            continue
    msg = "No Playwright browser found. Install at least one with:\n" + "\n".join(
        f"  playwright install {b}" for b in _BROWSER_PREFERENCE
    )
    rprint(f"[red]{msg}[/red]")
    raise RuntimeError(msg)


# ── login ─────────────────────────────────────────────────────────────────────


async def login(name: str, url: str) -> None:
    """Open a headed browser, let the user log in, then persist the session."""
    _require_playwright()
    from playwright.async_api import async_playwright
    from rich import print as rprint

    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    out = session_path(name)

    rprint(f"\n[bold]Opening browser for[/bold] [cyan]{name}[/cyan]…")
    rprint(f"[dim]URL: {url}[/dim]")
    rprint("[dim]Log in inside the browser window, then come back here and press Enter.[/dim]\n")

    async with async_playwright() as p:
        browser = await _launch_browser(p, headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, "Press Enter when you have finished logging in… ")

        await context.storage_state(path=str(out))
        out.chmod(0o600)  # session JSON contains auth cookies — restrict to owner
        await browser.close()

    _save_meta(name, url)
    rprint(f"[green]Session saved:[/green] {out}")


# ── browser download ──────────────────────────────────────────────────────────


async def browser_download(landing_url: str, dest: str, session_name: str) -> bool:
    """
    Navigate to landing_url using a saved session, find the PDF link, and
    save it to dest. Returns True on success.
    """
    state_file = session_path(session_name)
    if not state_file.exists():
        return False

    _require_playwright()
    from playwright.async_api import async_playwright

    from mosaic.downloader import looks_like_pdf

    async with async_playwright() as p:
        browser = await _launch_browser(p, headless=True)
        context = await browser.new_context(storage_state=str(state_file))
        page = await context.new_page()
        try:
            await page.goto(landing_url, wait_until="domcontentloaded", timeout=30_000)
            pdf_url = await _find_pdf_url(page)
            if not pdf_url:
                return False
            response = await context.request.get(pdf_url, timeout=120_000)
            if not response.ok:
                return False
            body = await response.body()
            if not looks_like_pdf(body):
                # Typically an HTML login/paywall page: the session is not
                # entitled to the PDF — let the caller try the next option.
                log.debug("Browser download from %s did not return a PDF", pdf_url)
                return False
            dest_path = Path(dest)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            part = dest_path.with_name(dest_path.name + ".part")
            try:
                part.write_bytes(body)
                os.replace(part, dest_path)
            except BaseException:
                part.unlink(missing_ok=True)
                raise
            return True
        except Exception:
            log.debug("Browser download failed for %s", landing_url, exc_info=True)
            return False
        finally:
            await browser.close()


async def _find_pdf_url(page) -> str | None:
    """Heuristically locate the PDF download URL on a publisher page."""
    # 1. CSS selector heuristics
    for selector in _PDF_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el:
                href = await el.get_attribute("href")
                if href:
                    return _absolutise(href, page.url)
        except Exception:
            log.debug("PDF selector %s failed", selector, exc_info=True)
            continue

    # 2. Text-based link search
    links = await page.query_selector_all("a[href]")
    for link in links:
        try:
            text = (await link.inner_text()).lower().strip()
            href = await link.get_attribute("href") or ""
            if any(pat in text for pat in _PDF_TEXT_PATTERNS) and href:
                return _absolutise(href, page.url)
        except Exception:
            log.debug("PDF text link search failed", exc_info=True)
            continue

    return None


def _absolutise(href: str, base_url: str) -> str:
    """Resolve *href* against the page URL (relative, root-relative or protocol-relative)."""
    return urljoin(base_url, href)


def _require_playwright() -> None:
    """Raise ImportError with install instructions if Playwright is missing.

    Library code must not exit the process: the web UI runs downloads in
    worker threads, and ``mosaic get --from`` must keep going with the next
    DOI.  The CLI turns this into a friendly message.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise ImportError(
            "Playwright is not installed.\n"
            "Install it with: pip install 'mosaic-search[browser]'\n"
            "Then run: playwright install chromium"
        ) from None


def has_browser() -> bool:
    """Return True if Playwright is installed and at least one browser binary exists."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    import sys

    pw_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not pw_path:
        if sys.platform == "darwin":
            pw_path = str(Path.home() / "Library/Caches/ms-playwright")
        elif sys.platform == "win32":
            pw_path = str(Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright")
        else:
            pw_path = str(Path.home() / ".cache/ms-playwright")
    p = Path(pw_path)
    return p.is_dir() and any(p.iterdir())
