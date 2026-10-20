"""Hand failed downloads to the user's own browser (``mosaic get --handoff``).

Some publishers block every automated browser (Elsevier answers any
Playwright-driven browser with HTTP 403, logged in or not). The only
legitimate way through is the user's normal browser, with their normal
logins. This module opens each paper there and watches the Downloads folder:
the next new PDF to appear is filed under the paper's name.

Papers are handed off in batches (one at a time by default). Each new PDF is
matched to a paper of the current batch by its file name or by the DOI it
carries. Nothing here automates the browser.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import select
import shutil
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

from mosaic.pdf import is_pdf_file

log = logging.getLogger(__name__)

# Browsers write here first and rename on completion.
_PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".download", ".tmp")


def is_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def _run(cmd: list[str], timeout: float = 20) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def default_downloads_dir() -> Path | None:
    """Return the folder the user's browser saves downloads to, if it can be found.

    On WSL that is the *Windows* Downloads known folder (which may have been
    moved, e.g. into OneDrive), asked from Windows and mapped with
    ``wslpath``; elsewhere ``xdg-user-dir DOWNLOAD`` or ``~/Downloads``.
    """
    candidates: list[str] = []
    if is_wsl():
        win = _run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path",
            ]
        )
        if win:
            candidates.append(_run(["wslpath", "-u", win]))
    else:
        candidates.append(_run(["xdg-user-dir", "DOWNLOAD"]))
    candidates.append(str(Path.home() / "Downloads"))
    for c in candidates:
        if c and Path(c).is_dir():
            return Path(c)
    return None


def open_in_browser(url: str) -> bool:
    """Open *url* in the user's default browser (the Windows one under WSL).

    ``explorer.exe`` opens File Explorer instead of the browser for a URL with
    a query string, so PowerShell's ``Start-Process`` comes before it.
    """
    if is_wsl():
        quoted = "'" + url.replace("'", "''") + "'"
        start = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Start-Process {quoted}",
        ]
        for cmd in (["wslview", url], start, ["explorer.exe", url]):
            if shutil.which(cmd[0]):
                try:
                    # explorer.exe exits 1 even on success: launching is what counts.
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
                except OSError:
                    continue
    return webbrowser.open(url)


def _snapshot(folder: Path) -> dict[str, tuple[int, float]]:
    out = {}
    for entry in os.scandir(folder):
        # Browsers create and rename temporary files (Chrome's
        # "Unconfirmed 123.crdownload") between the listing and the stat.
        try:
            if entry.is_file():
                st = entry.stat()
                out[entry.name] = (st.st_size, st.st_mtime)
        except OSError:
            continue
    return out


class DownloadWatcher:
    """Detect PDFs that finish downloading into *folder* after :meth:`arm`."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._before: dict[str, tuple[int, float]] = {}
        self._sizes: dict[str, int] = {}
        self._pending: set[str] = set()

    def arm(self) -> None:
        """Remember what is already there; only later arrivals count."""
        self._before = _snapshot(self.folder)
        self._sizes = {}
        self._pending = set()

    def downloading(self) -> bool:
        """True while a download is under way since :meth:`arm`.

        That is, a partial file (``.crdownload``, ``.part``, ...) exists, or a
        finished-looking file was seen once and awaits its confirming poll.
        """
        if self._pending:
            return True
        return any(
            name.lower().endswith(_PARTIAL_SUFFIXES) and name not in self._before
            for name in _snapshot(self.folder)
        )

    def ignore(self, path: Path) -> None:
        """Stop reporting *path* (a download that belongs to no paper)."""
        self._pending.discard(path.name)
        try:
            st = path.stat()
            self._before[path.name] = (st.st_size, st.st_mtime)
        except OSError:
            pass

    def poll(self) -> Path | None:
        """Return a completed new PDF, or None.

        A candidate must be new or modified since :meth:`arm`, have no partial
        companion (``x.pdf.crdownload``), keep the same size across two polls,
        and start with the PDF signature.
        """
        now = _snapshot(self.folder)
        names = set(now)
        for name, stat in sorted(now.items(), key=lambda kv: kv[1][1]):
            if name.lower().endswith(_PARTIAL_SUFFIXES) or self._before.get(name) == stat:
                continue
            if any(name + suffix in names for suffix in _PARTIAL_SUFFIXES):
                continue
            size = stat[0]
            if size == 0 or self._sizes.get(name) != size:
                self._sizes[name] = size  # still growing, or first sighting
                self._pending.add(name)
                continue
            self._pending.discard(name)
            path = self.folder / name
            if is_pdf_file(path):
                return path
            self._before[name] = stat  # a finished non-PDF: ignore from now on
        return None


def _collect(src: Path, dest: str, unlink_wait_s: float = 5.0) -> bool:
    """Copy *src* to *dest*, then remove *src*; return True if *src* was removed.

    A plain move fails on WSL: Downloads lives on the Windows drive, so the
    move is copy-then-delete, and Windows briefly locks a freshly downloaded
    file (typically antivirus scanning it). The copy is written to a
    ``.part`` file and renamed, so *dest* is never half-written; deleting the
    original is retried, and a file that stays locked is left in place.
    """
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    shutil.copyfile(src, part)
    part.replace(target)
    deadline = time.monotonic() + unlink_wait_s
    while True:
        try:
            src.unlink()
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            if time.monotonic() >= deadline:
                log.warning("Could not remove %s (locked); leaving it in place", src)
                return False
            time.sleep(0.5)


_IN_PROGRESS_MAX_S = 120.0

# ScienceDirect article URLs carry the PII, and its PDFs are saved as
# "1-s2.0-<PII>-main.pdf".
_PII_IN_URL = re.compile(r"/pii/([A-Z0-9]{10,})", re.I)
_MIN_ID_LEN = 6


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _filename_ids(key: str, url: str) -> list[str]:
    """Identifiers of a paper that publishers put in PDF file names.

    The ScienceDirect PII, and the DOI suffix (Springer saves
    ``s10915-021-01234-5.pdf`` for ``10.1007/s10915-021-01234-5``), normalised
    to lowercase alphanumerics.
    """
    ids = []
    m = _PII_IN_URL.search(url)
    if m:
        ids.append(_norm(m.group(1)))
    if key.startswith("10.") and "/" in key:
        suffix = _norm(key.split("/", 1)[1])
        if len(suffix) >= _MIN_ID_LEN:
            ids.append(suffix)
    return ids


def _first_pages_text(path: Path, pages: int = 2) -> str:
    """Text of the first *pages* pages, or "" without pymupdf or on failure."""
    try:
        import fitz
    except ImportError:
        return ""
    try:
        with fitz.open(str(path)) as doc:
            return " ".join(doc[i].get_text() for i in range(min(pages, len(doc))))
    except Exception:
        log.debug("Could not read text of %s", path, exc_info=True)
        return ""


def _doi_mentions(path: Path, dois: list[str]) -> list[str]:
    """The DOIs among *dois* that *path* mentions.

    Publishers write the DOI into the PDF metadata, which is stored
    uncompressed, and print it on the first page. A PDF also links the DOIs of
    the papers it cites, so a caller must treat several hits as ambiguous.
    """
    try:
        raw = path.read_bytes().lower()
    except OSError:
        return []
    text = _norm(_first_pages_text(path))
    return [d for d in dois if d.lower().encode() in raw or (text and _norm(d) in text)]


def _match(found: Path, pending: dict[str, tuple[str, str, str, str]]) -> str | None:
    """Return the key of the pending paper *found* belongs to, or None.

    Tried in order: an identifier in the file name, the paper's DOI inside the
    PDF, and, when one paper is left, that paper (the one-at-a-time rule).
    """
    name = _norm(found.name)
    by_name = [
        k for k, (_, _, url, _) in pending.items() if any(i in name for i in _filename_ids(k, url))
    ]
    if len(by_name) == 1:
        return by_name[0]
    by_doi = _doi_mentions(found, [k for k in pending if k.startswith("10.")])
    if len(by_doi) == 1:
        return by_doi[0]
    if len(pending) == 1:
        return next(iter(pending))
    return None


def _enter_pressed(timeout: float) -> bool:
    """Wait up to *timeout* s; return True if the user pressed Enter (TTY only)."""
    if not sys.stdin.isatty():
        time.sleep(timeout)
        return False
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        sys.stdin.readline()
        return True
    return False


def handoff_download(
    items: list[tuple[str, str, str, str]],
    watch_dir: Path,
    *,
    batch: int = 1,
    wait_s: float = 300,
    poll_s: float = 1.0,
    grace_s: float = 8.0,
    open_gap_s: float = 1.0,
    on_result: Callable[[str, str | None, str | None], None] | None = None,
    opener: Callable[[str], bool] = open_in_browser,
    announce: Callable[[int, int, str, str], None] | None = None,
    on_opened: Callable[[int], None] | None = None,
    on_unmatched: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Open papers in the user's browser and file the PDFs they download.

    Papers are opened *batch* at a time. Each new PDF in *watch_dir* is filed
    for the paper of the current batch it matches (see :func:`_match`); a PDF
    that matches none is left where it is.

    Parameters
    ----------
    items : list of (key, label, url, dest)
        *key* is the DOI when there is one; *label* is shown to the user;
        *dest* is where the PDF is moved to.
    watch_dir : Path
        The browser's download folder.
    batch : int
        Papers opened together. The batch ends when all its PDFs have arrived,
        when the user presses Enter, or after *wait_s* without a new PDF.
    on_result : callable, optional
        Called as ``on_result(key, dest_or_None, original_filename_or_None)``.
    announce : callable, optional
        Called as ``announce(n, total, label, url)`` before opening each paper.
    on_opened : callable, optional
        Called with the batch size once the batch is open.
    on_unmatched : callable, optional
        Called with the name of a downloaded PDF that matches no paper.

    Returns
    -------
    dict
        *key* -> saved path, for the papers that were collected.
    """
    watcher = DownloadWatcher(watch_dir)
    saved: dict[str, str] = {}
    batch = max(batch, 1)
    for first in range(0, len(items), batch):
        chunk = items[first : first + batch]
        watcher.arm()
        for n, (_, label, url, _) in enumerate(chunk, first + 1):
            if announce:
                announce(n, len(items), label, url)
            if not opener(url):
                log.warning("Could not open a browser for %s", url)
            if len(chunk) > 1:
                time.sleep(open_gap_s)  # a burst of tabs looks like a bot
        if on_opened:
            on_opened(len(chunk))
        pending = {item[0]: item for item in chunk}
        # Unmatched PDFs, retried after each match: once one paper is left,
        # a PDF that names nothing belongs to it.
        held: list[Path] = []

        def take(found: Path, pending: dict = pending, held: list = held) -> None:
            key = _match(found, pending)
            if key is None:
                watcher.ignore(found)
                held.append(found)
                return
            dest = pending.pop(key)[3]
            try:
                _collect(found, dest)
                saved[key] = dest
            except OSError:
                log.warning("Could not file %s as %s", found, dest, exc_info=True)
                watcher.ignore(found)
            if on_result:
                on_result(key, saved.get(key), found.name)
            for f in list(held):
                if pending and f.exists():
                    held.remove(f)
                    take(f)

        deadline = time.monotonic() + wait_s
        while pending and time.monotonic() < deadline:
            if _enter_pressed(poll_s):
                # Enter means "done with this batch", and users press it right
                # after clicking Download: keep polling while a download is
                # finishing instead of discarding it.
                start = time.monotonic()
                while pending:
                    found = watcher.poll()
                    if found:
                        take(found)
                        continue
                    elapsed = time.monotonic() - start
                    if elapsed >= _IN_PROGRESS_MAX_S or (
                        elapsed >= grace_s and not watcher.downloading()
                    ):
                        break
                    time.sleep(poll_s)
                break
            found = watcher.poll()
            if found:
                take(found)
                deadline = time.monotonic() + wait_s
        if on_unmatched:
            for f in held:
                if f.exists():
                    on_unmatched(f.name)
        if on_result:
            for key in pending:
                on_result(key, None, None)
    return saved
