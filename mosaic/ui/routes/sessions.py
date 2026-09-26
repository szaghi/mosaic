"""Saved browser sessions (``mosaic auth``)."""

from __future__ import annotations

from flask import flash, redirect, render_template, url_for

from mosaic.ui.routes.common import app_version, bp

# ---------------------------------------------------------------------------
# Auth sessions
# ---------------------------------------------------------------------------


@bp.route("/sessions")
def sessions_page():
    from mosaic.auth import list_sessions

    sessions = list_sessions()
    return render_template("sessions.html", sessions=sessions, version=app_version())


@bp.route("/sessions/delete/<name>", methods=["POST"])
def session_delete(name):
    from mosaic.auth import delete_session

    if delete_session(name):
        flash(f"Session '{name}' deleted.", "success")
    else:
        flash(f"No session found for '{name}'.", "warning")
    return redirect(url_for("ui.sessions_page"))
