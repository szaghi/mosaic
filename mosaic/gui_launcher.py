"""Entry point for the standalone MOSAIC app (PyInstaller)."""
from __future__ import annotations


def main() -> None:
    import sys
    import webview
    from mosaic.ui import create_app

    app = create_app()
    webview.create_window("MOSAIC", app, width=1200, height=800)
    # Force WebView2/Edge backend on Windows — avoids pythonnet (winforms) which
    # fails when bundled with PyInstaller due to DLL resolution issues.
    gui = "edgechromium" if sys.platform == "win32" else None
    webview.start(gui=gui)


if __name__ == "__main__":
    main()
