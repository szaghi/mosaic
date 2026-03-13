"""Entry point for the standalone MOSAIC app (PyInstaller)."""
from __future__ import annotations
import os
import sys

# Must be set before pythonnet/clr is imported (triggered by pywebview on Windows).
# pythonnet 3.x ships a CoreCLR build of Python.Runtime.dll; the netfx loader
# fails in PyInstaller bundles with "Failed to resolve Python.Runtime.Loader.Initialize".
# coreclr requires .NET 6+ Runtime to be installed on the target machine.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONNET_RUNTIME", "coreclr")


def main() -> None:
    import webview
    from mosaic.ui import create_app

    app = create_app()
    webview.create_window("MOSAIC", app, width=1200, height=800)
    gui = "edgechromium" if sys.platform == "win32" else None
    webview.start(gui=gui)


if __name__ == "__main__":
    main()
