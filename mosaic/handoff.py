"""Hand failed downloads to the user's own browser (``mosaic get --handoff``).

Some publishers block every automated browser (Elsevier answers any
Playwright-driven browser with HTTP 403, logged in or not). The only
legitimate way through is the user's normal browser, with their normal
logins. This module opens each paper there and watches the Downloads folder:
the next new PDF to appear is filed under the paper's name.

Papers are handed off one at a time, so each new PDF belongs to the paper the
user was just shown. Nothing here automates the browser.
"""

from __future__ import annotations

import logging
import os
import platform
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
    """Open *url* in the user's default browser (the Windows one under WSL)."""
    if is_wsl():
        for cmd in (["wslview", url], ["explorer.exe", url]):
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
        if entry.is_file():
            st = entry.stat()
            out[entry.name] = (st.st_size, st.st_mtime)
    return out


class DownloadWatcher:
    """Detect PDFs that finish downloading into *folder* after :meth:`arm`."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._before: dict[str, tuple[int, float]] = {}
        self._sizes: dict[str, int] = {}

    def arm(self) -> None:
        """Remember what is already there; only later arrivals count."""
        self._before = _snapshot(self.folder)
        self._sizes = {}

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
                continue
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
    wait_s: float = 300,
    poll_s: float = 1.0,
    on_result: Callable[[str, str | None, str | None], None] | None = None,
    opener: Callable[[str], bool] = open_in_browser,
    announce: Callable[[int, int, str, str], None] | None = None,
) -> dict[str, str]:
    """Open each paper in the user's browser and file the PDF they download.

    Parameters
    ----------
    items : list of (key, label, url, dest)
        *label* is shown to the user; *dest* is where the PDF is moved to.
    watch_dir : Path
        The browser's download folder.
    on_result : callable, optional
        Called as ``on_result(key, dest_or_None, original_filename_or_None)``.
    announce : callable, optional
        Called as ``announce(n, total, label, url)`` before opening each paper.

    Returns
    -------
    dict
        *key* -> saved path, for the papers that were collected.
    """
    watcher = DownloadWatcher(watch_dir)
    saved: dict[str, str] = {}
    for n, (key, label, url, dest) in enumerate(items, 1):
        watcher.arm()
        if announce:
            announce(n, len(items), label, url)
        if not opener(url):
            log.warning("Could not open a browser for %s", url)
        found: Path | None = None
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if _enter_pressed(poll_s):
                break
            found = watcher.poll()
            if found:
                break
        if found:
            try:
                _collect(found, dest)
                saved[key] = dest
            except OSError:
                log.warning("Could not file %s as %s", found, dest, exc_info=True)
        if on_result:
            on_result(key, saved.get(key), found.name if found else None)
    return saved
