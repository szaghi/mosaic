"""MOSAIC web UI — Flask application factory."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask

import mosaic.config as cfg_mod
from mosaic.db import Cache
from mosaic.ui.jobs import JobManager


def _ui_base_path() -> Path:
    """Return the base path for UI templates and static files.

    When running inside a PyInstaller bundle, files are unpacked under
    ``sys._MEIPASS``; otherwise use the normal package directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "mosaic" / "ui"  # type: ignore[attr-defined]
    return Path(__file__).parent


def create_app() -> Flask:
    base = _ui_base_path()
    app = Flask(
        __name__,
        template_folder=str(base / "templates"),
        static_folder=str(base / "static"),
    )
    app.secret_key = os.urandom(24)

    cfg = cfg_mod.load()
    app.config["MOSAIC_CFG"] = cfg
    app.config["MOSAIC_CACHE"] = Cache(cfg["db_path"])
    app.config["JOB_MANAGER"] = JobManager()

    from mosaic.ui.routes import bp
    app.register_blueprint(bp)

    return app
