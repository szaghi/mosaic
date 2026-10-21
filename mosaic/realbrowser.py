"""Automated real-browser PDF pass (``mosaic get --auto``).

The publishers' PDF endpoints sit behind bot-fingerprinting (Cloudflare on
ScienceDirect; the signed asset host is guarded too), so only a *genuine*
Chrome ever receives the bytes. This module therefore drives the user's own
Chromium binary - the system install, a dedicated mosaic profile - over the
Chrome DevTools Protocol, through the same moves a human makes: open the
article, open its "Download PDF" link, let Chrome save the file natively, and
pick it up from a mosaic-owned download folder.

Nothing is disguised: the browser is a normal Chrome executing normal
navigations at human-compatible pace.

Measured realities that shape the flow (step-1 probe, 2026-10):

- The publisher chain is ``article -> /pdfft (md5-signed) ->
  /pdfft?crasolve=1 -> <asset host>/main.pdf``. Plain HTTP clients of any TLS
  fingerprint get 403 on these URLs even with valid session cookies.
- The interstitial page launches the transfer itself: ``window.onload`` ->
  ``redirectUser()`` plus a 5-second retry sets ``window.location`` to the
  presigned asset, and ``window.sdUserRedirected`` turns true when it ran.
  If the natural launch stalls, firing ``redirectUser()`` from the page (or
  assigning the scraped asset URL) is the proven manual backup.
- Downloads must be claimed at the *browser* level with
  ``Browser.setDownloadBehavior(behavior="allow", downloadPath=<folder>)``
  over a raw CDP session: without it, driver-side download pipelining
  silently swallows the transfers of pages created over CDP.
- The initiating page of the download must stay open until the PDF is filed
  (closing it cancels an in-flight transfer).
- Publisher session cookies (``sd_session_id`` ...) die with the browser
  process: after a fresh launch the first paper may need one login.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from mosaic import handoff
from mosaic.downloader import resolve_landing
from mosaic.errors import DependencyError

log = logging.getLogger(__name__)

# ── browser discovery and profile management ─────────────────────────────────

_DEBUG_PORT = 9222
_LA_TIMEOUT_S = 30.0

_WSL_CHROME_CANDIDATES = (
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
)
_LINUX_CHROME_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
)


def profile_dir() -> Path:
    """Dedicated browser profile mosaic controls (cookies persist across runs).

    On WSL it lives on the Windows side: the Windows Chrome cannot use a
    ``\\wsl$`` path. Elsewhere under ``~/.local/share``.
    """
    if handoff.is_wsl():
        user = handoff._run(["cmd.exe", "/c", "echo", "%USERNAME%"]).strip()
        return Path("/mnt/c/Users") / user / "mosaic-cdp-profile"
    return Path.home() / ".local/share/mosaic/browser-profile"


def download_folder() -> Path:
    """The browser download folder mosaic files PDFs from, WSL-mapped."""
    if handoff.is_wsl():
        user = handoff._run(["cmd.exe", "/c", "echo", "%USERNAME%"]).strip()
        return Path("/mnt/c/Users") / user / "mosaic-auto-downloads"
    return Path.home() / ".local/share/mosaic/browser-downloads"


def windows_path(path: Path) -> str:
    """Windows path for *path* (``wslpath -w``); passthrough elsewhere."""
    if not handoff.is_wsl():
        return str(path)
    out = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, check=False)
    return out.stdout.strip() or str(path)


def find_chrome() -> Path | None:
    """A chromium-family binary mosaic can drive over CDP, or None."""
    if handoff.is_wsl():
        for c in _WSL_CHROME_CANDIDATES:
            if Path(c).exists():
                return Path(c)
        return None
    for name in _LINUX_CHROME_NAMES:
        which = shutil.which(name)
        if which:
            return Path(which)
    return None


def _launch_args() -> list[str]:
    return [
        f"--remote-debugging-port={_DEBUG_PORT}",
        f"--user-data-dir={windows_path(profile_dir())}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "about:blank",
    ]


def _launch(exe: Path) -> None:
    if handoff.is_wsl():
        win = windows_path(exe)
        cmd = [
            "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Start-Process",
            f"-FilePath '{win}'",
            "-ArgumentList",
            ",".join(f"'{a}'" for a in _launch_args()),
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.Popen(
        [str(exe), *_launch_args()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _port_open(port: int = _DEBUG_PORT, timeout: float = 1.5) -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_port_open(seconds: float = _LA_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _port_open():
            return True
        time.sleep(0.5)
    return False


def set_pdf_download_prefs() -> None:
    """Make the profile save PDFs as downloads into our folder.

    Written only while the browser is closed (a running instance overwrites
    the file on exit). ``Browser.setDownloadBehavior`` below claims the same
    behaviour at the protocol level for a running instance, so this matters
    across restarts only.
    """
    prefs = profile_dir() / "Default" / "Preferences"
    try:
        prefs.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(prefs.read_text(encoding="utf-8")) if prefs.exists() else {}
        data.setdefault("plugins", {})["always_open_pdf_externally"] = True
        dl = data.setdefault("download", {})
        dl["default_directory"] = windows_path(download_folder())
        dl["prompt_for_download"] = False
        # Chromium's "multiple downloads" guard: a scripted site downloading
        # several files is blocked after the first, silently. Allow it in this
        # dedicated profile (a global default plus per-host exceptions).
        profile = data.setdefault("profile", {})
        profile.setdefault("default_content_setting_values", {})["automatic_downloads"] = 1
        exceptions = (
            profile.setdefault("content_settings", {})
            .setdefault("exceptions", {})
            .setdefault("automatic_downloads", {})
        )
        for host in (
            "https://www.sciencedirect.com:443,*",
            "https://pdf.sciencedirectassets.com:443,*",
        ):
            exceptions.setdefault(host, {"setting": 1})
        prefs.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        log.debug("could not pre-seed %s", prefs, exc_info=True)


# ── publisher page pieces ────────────────────────────────────────────────────

# Station cookies whose presence (scoped to the article host) signals a login.
_LOGIN_COOKIE_HINTS = ("sd_session_id", "idp_session", "_shibsession_", "pd_session")

# ScienceDirect's interstitial fires the transfer from its own JS.
_FIRE_REDIRECT = """() => {
  try {
    if (window.sdUserRedirected) return 'already-redirected';
    if (typeof redirectUser === 'function') { redirectUser(); return 'fired'; }
  } catch (e) { /* fall through to the snippet route */ }
  return 'no-fn';
}"""

_ASSET_URL_RE = re.compile(r'https://pdf\.sciencedirectassets\.com/[^\s"\'<>]+')

_PDF_LINKS_JS = """(pii) => {
  const ok = (u) => !pii || u.toUpperCase().includes(pii);
  const out = [];
  const meta = document.querySelector('meta[name="citation_pdf_url"]');
  if (meta && meta.content && ok(meta.content)) out.push(meta.content);
  for (const a of document.querySelectorAll('a[href]')) {
    if (!a.href) continue;
    const h = a.href.toUpperCase();
    const isPdf = h.includes('/PDFFT') || h.includes('PDFDIRECT') ||
      h.endsWith('.PDF') || h.includes('/DOI/PDF/') || h.includes('/DOI/EPDF/');
    if (isPdf && ok(a.href)) out.push(a.href);
  }
  return Array.from(new Set(out)).slice(0, 5);
}"""

# Journal DOIs resolve over HTTP only as far as Elsevier's linkinghub, whose
# page jumps to ScienceDirect via a delayed <meta refresh> the HEAD request
# cannot follow: a real navigation can, so the hop handles it implicitly.
_LINKINGHUB = "linkinghub.elsevier.com"


def _signed_asset_url(html: str) -> str | None:
    m = _ASSET_URL_RE.search(html)
    if not m:
        return None
    return m.group(0).replace("&amp;", "&").replace("\\u0026", "&")


def extract_pii(url: str) -> str | None:
    m = handoff._PII_IN_URL.search(url or "")
    return m.group(1).upper() if m else None


def _name_ids(paper_key: str, article_url: str) -> list[str]:
    """Lowercase-alphanumerics identifiers the PDF file name may carry.

    The ScienceDirect PII (``1-s2.0-<PII>-main.pdf``) and the DOI suffix
    (``s10915-...-5.pdf`` on Springer), plus the bare PII again because some
    publishers place it differently. Deduplicated.
    """
    ids: list[str] = handoff._filename_ids(paper_key, article_url)
    pii = extract_pii(article_url)
    if pii:
        n = handoff._norm(pii)
        if n not in ids:
            ids.append(n)
    return ids


# ── per-paper flow (async; tests drive it with in-memory fakes) ──────────────


@dataclass
class AutoItem:
    key: str
    url: str
    dest: str
    label: str = ""


async def poll_pdf_links(
    article, pii: str | None, seconds: float = 30.0, step_s: float = 1.5
) -> list[str]:
    """Read the article page for PDF links until they appear, or give up.

    A direct article hit can land through a challenge or hydration delay; the
    organic doi.org chain resolves before the DOM settles. Polling makes the
    one-shot evaluation robust for both.
    """
    deadline = time.monotonic() + seconds
    while True:
        try:
            links = await article.evaluate(_PDF_LINKS_JS, pii)
        except Exception:
            links = []
        if links:
            return links
        if time.monotonic() >= deadline:
            return []
        await asyncio.sleep(step_s)


_LOGIN_MARKERS = (
    "sign in",
    "log in",
    "login required",
    "sign-in",
    "log-in",
    "institutional access",
    "your institution",
)

_CHALLENGE_MARKERS = ("verify you are human", "just a moment", "checking your browser", "captcha")


async def classify_hop_wall(hop) -> str:
    """Classify why a hop produced no PDF: "login-required", "challenge", or "".

    Runs *after* the download watcher came up empty, so an interstitial with a
    slow asset is never mis-read: the only question left is what the page is.
    """
    try:
        url = (hop.url or "").lower()
    except Exception:
        url = ""
    if "id.elsevier.com" in url or "/user/login" in url or url.startswith("https://idp"):
        return "login-required"
    try:
        html = (await hop.content()) or ""
    except Exception:
        return ""
    low = html.lower()
    if len(html) < 4000:  # a thrown-away challenge shell
        return "challenge"
    for m in _CHALLENGE_MARKERS:
        if m in low:
            return "challenge"
    for m in _LOGIN_MARKERS:
        if m in low:
            return "login-required"
    return ""


async def download_one(
    ctx,
    item: AutoItem,
    *,
    natural_wait_s: float = 8.0,
    hop_wait_s: float = 75.0,
    link_wait_s: float = 30.0,
    poll_s: float = 1.0,
) -> str:
    """Download one paper through the real browser.

    Returns the destination path on success, ``"login-required"`` when the
    article page demanded a login, or ``None`` when no PDF could be fetched.
    """
    folder = download_folder()
    folder.mkdir(parents=True, exist_ok=True)

    article = None
    hop = None
    try:
        article = await ctx.new_page()
        await article.goto(item.url, wait_until="domcontentloaded", timeout=45_000)
        url = article.url or ""
        if "linkinghub" in url:
            try:
                await article.wait_for_url("*sciencedirect.com*", timeout=30_000)
            except Exception:
                log.debug("linkinghub redirect did not complete for %s", item.key)
            url = article.url or ""
        if "id.elsevier.com" in url or "/user/login" in url:
            log.debug("login wall for %s at %s", item.key, url[:100])
            return "login-required"

        pii = extract_pii(url)
        ids = _name_ids(item.key, url)
        links = await poll_pdf_links(article, pii, seconds=link_wait_s)
        log.debug("%s: landed %s, pii=%s, %d pdf link(s)", item.key, url[:80], pii, len(links))
        if not links:
            log.debug("no PDF link found on %s", url)
            return None

        watcher = handoff.DownloadWatcher(folder)
        watcher.arm()

        # The hop happens on a SECOND page; the article page stays open, since
        # closing the initiating page cancels an in-flight download.
        hop = await ctx.new_page()
        try:
            await hop.goto(links[0], referer=article.url, wait_until="commit", timeout=60_000)
        except Exception:
            log.debug("hop navigation aborted (download conversion), %s", item.key)
        # a hop that lands on the identity or sign-in pages means the session
        # has expired even if the article page did not demand a login before
        wall = await classify_hop_wall(hop)
        if wall == "login-required":
            log.debug("hop hit the login wall for %s", item.key)
            return "login-required"

        async def poll(seconds: float) -> Path | None:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                found = watcher.poll()
                if found is None:
                    await asyncio.sleep(poll_s)
                    continue
                nm = handoff._norm(found.name)
                if nm and any(i in nm for i in ids):
                    return found
                watcher.ignore(found)  # another tab's file; keep watching
                deadline = min(deadline, time.monotonic() + seconds)
            return None

        found = await poll(natural_wait_s)
        if found is None:
            state = ""
            try:
                state = await hop.evaluate(_FIRE_REDIRECT) or ""
            except Exception:
                log.debug("redirectUser probe failed for %s", item.key, exc_info=True)
            if "fired" not in state:
                log.debug(
                    "natural launch stalled for %s (state=%r); firing manually", item.key, state
                )
                try:
                    asset = _signed_asset_url(await hop.content())
                    if asset:
                        try:
                            await hop.evaluate("(u) => { window.location = u; }", asset)
                        except Exception:
                            pass  # navigation aborts when it becomes a download
                except Exception:
                    log.debug("could not scrape asset URL for %s", item.key, exc_info=True)
            found = await poll(hop_wait_s)
        if found is None:
            # the identity/challenge redirect can also arrive only in the
            # timeout window, after the hop's own async forward
            wall = await classify_hop_wall(hop)
            if wall == "login-required":
                log.debug("late login redirect for %s", item.key)
                return "login-required"
            log.debug(
                "no download arrived for %s within %0.f+%0.f s (page=%r)",
                item.key,
                natural_wait_s,
                hop_wait_s,
                wall,
            )
            return None

        data = found.read_bytes()
        off = data[:8192].find(b"%PDF-")
        if off < 0:
            log.debug("downloaded %s is not a PDF", found.name)
            return None
        # _collect writes dest via a .part sibling and deletes the original
        # (with a Windows-lock retry), so dest is never half-written.
        handoff._collect(found, item.dest)
        return item.dest
    except Exception:
        log.debug("real-browser download failed for %s", item.key, exc_info=True)
        return None
    finally:
        for pg in (hop, article):
            if pg is not None:
                try:
                    await pg.close()
                except Exception:
                    pass


async def _has_login_cookie(ctx, url: str = "") -> bool:
    """True when a publisher login cookie exists.

    The hint names are short-lived session cookies that only exist while the
    publisher considers the browser logged in. The lookup scoped to *url*'s
    host cannot see a ScienceDirect login from a doi.org URL, so when the
    scoped jar is empty the whole cookie jar is checked as a fallback.
    """
    for scope in ([url] if url else []) + [None]:
        try:
            cookies = await (ctx.cookies(scope) if scope else ctx.cookies())
        except TypeError:
            try:
                cookies = await ctx.cookies()
            except Exception:
                cookies = []
        except Exception:
            continue
        names = {c.get("name", "") for c in cookies}
        if any(h in n for n in names for h in _LOGIN_COOKIE_HINTS):
            return True
    return False


async def login_wait(
    ctx, url: str, *, wait_s: float = 180.0, prompt: Callable[[str], None] | None = None
) -> tuple[bool, bool]:
    """Wait for the user to complete the SSO in the visible browser.

    *prompt* receives the article URL (the CLI prints guidance). Pressing
    Enter in the terminal skips ahead; a login cookie appearing for *url*
    ends the wait successfully.

    Returns ``(login_visible, user_skipped)``: the retry decision belongs to
    the caller, since a login cookie mosaic does not recognize by name is
    still a real login.
    """
    if prompt:
        prompt(url)
    skip = asyncio.Event()
    loop = asyncio.get_running_loop()
    if sys.stdin.isatty():
        loop.add_reader(sys.stdin, skip.set)
    try:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if skip.is_set():
                return await _has_login_cookie(ctx, url), True
            if await _has_login_cookie(ctx, url):
                return True, False
            await asyncio.sleep(3)
        return False, False  # timed out: the user may still have logged in
    finally:
        if sys.stdin.isatty():
            try:
                loop.remove_reader(sys.stdin)
            except Exception:
                pass


async def connect(p, exe: Path):
    """Attach to the debug Chrome, launching it when absent; return (b, ctx)."""
    if _port_open():
        try:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_DEBUG_PORT}")
            ctx = browser.contexts[0] if browser.contexts else None
            if browser is not None and ctx is not None:
                return browser, ctx
        except Exception:
            log.debug("attach to running Chrome failed", exc_info=True)
    set_pdf_download_prefs()
    _launch(exe)
    if not await asyncio.to_thread(_wait_port_open):
        raise DependencyError(
            "Launched Chrome but its debug port never opened. "
            "Close stray Chrome windows using the mosaic profile and retry."
        )
    browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_DEBUG_PORT}")
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    return browser, ctx


async def auto_download(
    items: list[AutoItem],
    *,
    on_result: Callable[[str, str | None, str], None] | None = None,
    prompt_login: Callable[[str], None] | None = None,
    politeness_s: tuple[float, float] = (8.0, 15.0),
    max_papers: int = 50,
    block_abort_after: int = 3,
) -> dict[str, str]:
    """Drive the real browser over *items*; return ``key -> saved path``.

    Guardrails: strictly sequential papers, a jittered delay between them, a
    per-run cap, and a hard stop after *block_abort_after* consecutive
    login/challenge walls (never hammer a publisher that is deflecting).

    ``on_result(key, path_or_None, note)`` runs after every paper; the note is
    "" on success or the reason for a skip.
    """
    if not items:
        return {}
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        # only the CDP client is needed: no `playwright install`, the browser is the system one
        raise DependencyError(
            "Playwright is not installed. Install it with: pip install 'mosaic-search[browser]'"
        ) from None

    exe = find_chrome()
    if exe is None:
        raise DependencyError(
            "No Chrome/Edge found to drive: install Google Chrome (or Edge), "
            'then retry with "mosaic get <doi> --auto".'
        )
    saved: dict[str, str] = {}

    async with async_playwright() as p:
        browser, ctx = await connect(p, exe)
        try:
            # Claim downloads at the protocol level: driver-side pipelining
            # otherwise swallows the transfers of CDP-attached pages.
            try:
                bsess = await browser.new_browser_cdp_session()
                await bsess.send(
                    "Browser.setDownloadBehavior",
                    {
                        "behavior": "allow",
                        "downloadPath": windows_path(download_folder()),
                        "eventsEnabled": True,
                    },
                )
            except Exception:
                log.debug("could not claim download behavior", exc_info=True)

            # ── group by publisher site ─────────────────────────────────────
            # one site's walls must never starve the others: each site gets
            # its own attempts and its own guardrail.
            buckets: dict[str, list[AutoItem]] = {}
            for it in items:
                try:
                    site = urlparse(resolve_landing(it.url)).netloc or urlparse(it.url).netloc
                except Exception:
                    site = urlparse(it.url).netloc
                if not site and it.dest.startswith(("http://", "https://")):
                    site = urlparse(it.dest).netloc
                buckets.setdefault(site or "unknown", []).append(it)

            attempted = 0
            brought_up: set[str] = set()
            for site, bucket in buckets.items():
                site_blocked = 0
                for n, item in enumerate(bucket, 1):
                    if attempted >= max_papers:
                        for rest in bucket[n - 1 :]:
                            if on_result:
                                on_result(rest.key, None, "skipped: over the per-run cap")
                        break
                    attempted += 1
                    outcome = await download_one(ctx, item)
                    if outcome and outcome != "login-required":
                        site_blocked = 0
                        saved[item.key] = outcome
                        if on_result:
                            on_result(item.key, outcome, "")
                    elif outcome == "login-required":
                        # a login wall is not a publisher deflection: never
                        # count it toward the abort; prompt its site once
                        if site not in brought_up and prompt_login:
                            brought_up.add(site)
                            page = await ctx.new_page()
                            try:
                                await page.goto(
                                    item.url, wait_until="domcontentloaded", timeout=45_000
                                )
                                _, skipped = await login_wait(ctx, item.url, prompt=prompt_login)
                            except Exception:
                                skipped = False
                            try:
                                await page.close()
                            except Exception:
                                pass
                            if not skipped:
                                # the user may have logged in even when the
                                # hint names do not recognize the cookie:
                                # the retry is the proof
                                outcome = await download_one(ctx, item)
                                if outcome and outcome != "login-required":
                                    saved[item.key] = outcome
                                    if on_result:
                                        on_result(item.key, outcome, "")
                        if on_result and item.key not in saved:
                            on_result(item.key, None, "login required")
                    else:
                        site_blocked += 1
                        if on_result:
                            on_result(item.key, None, "no PDF arrived")

                    if site_blocked >= block_abort_after:
                        log.warning(
                            "%d consecutive walls at %s: skipping that site",
                            site_blocked,
                            site or "(unknown)",
                        )
                        for rest in bucket[n:]:
                            if on_result:
                                on_result(rest.key, None, "stopped: repeated walls")
                        break
                    if n < len(bucket) and politeness_s:
                        lo, hi = politeness_s
                        await asyncio.sleep(random.uniform(lo, hi))  # noqa: S311
                if attempted < max_papers and politeness_s != (0.0, 0.0):
                    await asyncio.sleep(3)  # a pause between publisher sites
        finally:
            try:
                await browser.close()
            except Exception:
                log.debug("browser close failed", exc_info=True)

    return saved


def auto_download_sync(
    items: list[tuple[str, str, str, str]],
    *,
    on_result: Callable[[str, str | None, str], None] | None = None,
    prompt_login: Callable[[str], None] | None = None,
    politeness_s: tuple[float, float] = (8.0, 15.0),
    max_papers: int = 50,
) -> tuple[dict[str, str], str]:
    """Sync wrapper: items as ``(key, label, url, dest)``.

    Returns ``(saved, state)`` where state is "", "dependency", or "failed":
    callers keep offering ``--interactive``/``--handoff`` on any state change.
    """
    real = [AutoItem(key=k, url=u, dest=d, label=lab) for k, lab, u, d in items]
    try:
        saved = asyncio.run(
            auto_download(
                real,
                on_result=on_result,
                prompt_login=prompt_login,
                politeness_s=politeness_s,
                max_papers=max_papers,
            )
        )
        if not saved:
            return {}, "failed"
        return saved, ""
    except DependencyError as e:
        log.warning("auto pass unavailable: %s", e)
        return {}, "dependency"
    except Exception:
        log.warning("auto pass crashed", exc_info=True)
        return {}, "failed"
