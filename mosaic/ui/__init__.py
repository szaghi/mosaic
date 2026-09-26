"""MOSAIC web UI — Flask application factory."""

from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from flask import Flask, redirect, request, session

import mosaic.config as cfg_mod
from mosaic.db import Cache
from mosaic.ui.jobs import JobManager

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# Bind addresses meaning "all interfaces" (compared against, never bound here)
_WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::"})  # noqa: S104
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _ui_base_path() -> Path:
    """Return the base path for UI templates and static files.

    When running inside a PyInstaller bundle, files are unpacked under
    ``sys._MEIPASS``; otherwise use the normal package directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "mosaic" / "ui"  # type: ignore[attr-defined]
    return Path(__file__).parent


def _hostname(netloc: str) -> str:
    """Return the lower-cased host part of ``host[:port]`` (IPv6-aware)."""
    return (urlsplit(f"//{netloc}").hostname or "").lower()


def allowed_hosts_for(bind_host: str) -> frozenset[str] | None:
    """Host names accepted in the ``Host`` header, or ``None`` for "any".

    Restricting the Host header defeats DNS-rebinding attacks, where a
    malicious page resolves its own domain to 127.0.0.1 and reads the UI
    (including the configuration page) from the victim's browser.
    """
    host = bind_host.strip().strip("[]").lower()
    if host in _WILDCARD_HOSTS:
        return None
    return _LOOPBACK_HOSTS | {host}


def _is_cross_origin() -> bool:
    """True when a browser tells us the request was issued by another site."""
    fetch_site = request.headers.get("Sec-Fetch-Site")
    if fetch_site and fetch_site not in ("same-origin", "none"):
        return True
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        # Non-browser clients (curl, scripts, tests) send neither header
        return False
    if source == "null":
        return True
    return urlsplit(source).netloc.lower() != request.host.lower()


def is_loopback(bind_host: str) -> bool:
    """True when *bind_host* only accepts connections from this machine."""
    return bind_host.strip().strip("[]").lower() in _LOOPBACK_HOSTS


_AUTH_REQUIRED_PAGE = (
    "<!doctype html><title>MOSAIC — access token required</title>"
    "<h1>Access token required</h1>"
    "<p>This MOSAIC web UI is reachable from the network and requires an access token. "
    "Open the URL printed by <code>mosaic ui</code> (it ends with <code>?token=…</code>).</p>"
)


def _token_matches(candidate: str | None, token: str) -> bool:
    return bool(candidate) and hmac.compare_digest(candidate.encode(), token.encode())


def create_app(*, bind_host: str = "127.0.0.1", access_token: str | None = None) -> Flask:
    base = _ui_base_path()
    app = Flask(
        __name__,
        template_folder=str(base / "templates"),
        static_folder=str(base / "static"),
    )
    app.secret_key = os.urandom(24)
    app.config["SESSION_COOKIE_SAMESITE"] = "Strict"

    cfg = cfg_mod.load()
    app.config["MOSAIC_CFG"] = cfg
    app.config["MOSAIC_CACHE"] = Cache(cfg["db_path"])
    app.config["JOB_MANAGER"] = JobManager()
    app.config["ALLOWED_HOSTS"] = allowed_hosts_for(bind_host)

    @app.before_request
    def _guard_request():
        allowed = app.config.get("ALLOWED_HOSTS")
        if allowed is not None and _hostname(request.host) not in allowed:
            return "Forbidden: unexpected Host header.", 403
        if access_token and not session.get("mosaic_auth"):
            # Scripts may send the token as a bearer header on every request;
            # browsers present it once as ?token=… and then use the session cookie.
            bearer = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not _token_matches(bearer, access_token):
                if not _token_matches(request.args.get("token"), access_token):
                    return _AUTH_REQUIRED_PAGE, 401
                session["mosaic_auth"] = True
                # Drop the token from the address bar (history, Referer headers)
                args = {k: v for k, v in request.args.items(multi=True) if k != "token"}
                query = f"?{urlencode(args)}" if args else ""
                return redirect(f"{request.path}{query}")
        # The UI has no login: refuse state-changing requests coming from
        # other origins (CSRF), e.g. a web page posting to /config.
        if request.method not in _SAFE_METHODS and _is_cross_origin():
            return "Forbidden: cross-origin request blocked.", 403
        return None

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    from mosaic.ui.routes import bp

    app.register_blueprint(bp)

    return app
