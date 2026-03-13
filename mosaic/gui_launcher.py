"""Entry point for the standalone MOSAIC app (PyInstaller)."""
from __future__ import annotations
import os
import platform
import shutil
import subprocess
import threading
import time
import webbrowser

_PORT = 5555


def _find_browser() -> tuple[str, bool] | tuple[None, bool]:
    """Return ``(path, supports_app_mode)`` or ``(None, False)``.

    Prefers Chromium-based browsers (Chrome / Edge / Chromium) because they
    support ``--app=URL`` for a clean, chrome-less window.  Falls back to
    Firefox which is opened with ``--new-window`` instead.
    """
    system = platform.system()

    # -- Chromium-family (supports --app) ------------------------------------
    if system == "Windows":
        candidates: list[str] = []
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env, "")
            if not base:
                continue
            candidates += [
                os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
        for path in candidates:
            if os.path.isfile(path):
                return path, True
        # Firefox on Windows
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(env, "")
            if not base:
                continue
            ff = os.path.join(base, "Mozilla Firefox", "firefox.exe")
            if os.path.isfile(ff):
                return ff, False

    elif system == "Darwin":
        for app in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ):
            if os.path.isfile(app):
                return app, True
        ff = "/Applications/Firefox.app/Contents/MacOS/firefox"
        if os.path.isfile(ff):
            return ff, False

    else:  # Linux / BSD
        for name in ("google-chrome", "google-chrome-stable", "chromium-browser",
                      "chromium", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                return found, True
        for name in ("firefox", "firefox-esr"):
            found = shutil.which(name)
            if found:
                return found, False

    return None, False


def _open_app_window(url: str) -> None:
    """Open *url* in a dedicated window.

    Chromium-based browsers get ``--app=URL`` (no address bar / tabs).
    Firefox gets ``--new-window`` (separate window, still has chrome).
    Falls back to the default browser if nothing is found.
    """
    time.sleep(0.8)
    browser, app_mode = _find_browser()
    if browser and app_mode:
        subprocess.Popen(
            [browser, f"--app={url}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif browser:
        subprocess.Popen(
            [browser, "--new-window", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        webbrowser.open(url)


def main() -> None:
    from waitress import serve
    from mosaic.ui import create_app

    app = create_app()
    url = f"http://127.0.0.1:{_PORT}"

    threading.Thread(target=_open_app_window, args=(url,), daemon=True).start()
    serve(app, host="127.0.0.1", port=_PORT, threads=4)


if __name__ == "__main__":
    main()
