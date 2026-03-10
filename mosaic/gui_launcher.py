"""Entry point for the standalone MOSAIC app (PyInstaller).

Starts the web UI server and opens the default browser.
"""
from __future__ import annotations

import sys
import threading
import webbrowser


def main() -> None:
    host, port = "127.0.0.1", 5555

    from mosaic.ui import create_app
    from waitress import create_server

    app = create_app()
    threading.Timer(1.5, webbrowser.open, args=[f"http://{host}:{port}"]).start()

    server = create_server(app, host=host, port=port)
    try:
        server.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
