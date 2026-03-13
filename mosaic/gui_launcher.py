"""Entry point for the standalone MOSAIC app (PyInstaller)."""
from __future__ import annotations
import threading
import time
import webbrowser

_PORT = 5555


def main() -> None:
    from waitress import serve
    from mosaic.ui import create_app

    app = create_app()

    def _open_browser() -> None:
        time.sleep(0.8)
        webbrowser.open(f"http://127.0.0.1:{_PORT}")

    threading.Thread(target=_open_browser, daemon=True).start()
    serve(app, host="127.0.0.1", port=_PORT, threads=4)


if __name__ == "__main__":
    main()
