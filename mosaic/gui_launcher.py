"""Entry point for the standalone MOSAIC app (PyInstaller)."""
from __future__ import annotations


def main() -> None:
    import webview
    from mosaic.ui import create_app

    app = create_app()
    webview.create_window("MOSAIC", app, width=1200, height=800)
    webview.start()


if __name__ == "__main__":
    main()
