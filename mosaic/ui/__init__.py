"""MOSAIC web UI — Flask application factory."""
from __future__ import annotations

import os

from flask import Flask

import mosaic.config as cfg_mod
from mosaic.db import Cache
from mosaic.ui.jobs import JobManager


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.urandom(24)

    cfg = cfg_mod.load()
    app.config["MOSAIC_CFG"] = cfg
    app.config["MOSAIC_CACHE"] = Cache(cfg["db_path"])
    app.config["JOB_MANAGER"] = JobManager()

    from mosaic.ui.routes import bp
    app.register_blueprint(bp)

    return app
