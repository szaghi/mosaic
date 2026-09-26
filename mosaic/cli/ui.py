"""The ``ui`` command (local web interface)."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import print as rprint

from mosaic.cli.app import app


@app.command()
def ui(
    host: Annotated[str, typer.Option(help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port number")] = 5555,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Don't auto-open browser")
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable Flask debug mode")] = False,
    token: Annotated[
        str,
        typer.Option(
            "--token",
            envvar="MOSAIC_UI_TOKEN",
            help="Access token required by the UI (default: random when --host is not loopback)",
        ),
    ] = "",
    no_auth: Annotated[
        bool,
        typer.Option(
            "--no-auth", help="Disable the access token even on a network-reachable address"
        ),
    ] = False,
):
    """Launch the MOSAIC web interface."""
    try:
        from mosaic.ui import create_app
    except ImportError:
        rprint("[red]Flask is required for the web UI. Install it with:[/red]")
        rprint("  pip install 'mosaic-search[ui]'")
        raise typer.Exit(1) from None

    import secrets

    from mosaic.ui import allowed_hosts_for, is_loopback

    if no_auth:
        token = ""
    elif not token and not is_loopback(host):
        token = secrets.token_urlsafe(24)

    if not is_loopback(host):
        if token:
            rprint(
                f"[dark_orange]Binding to {host}:[/dark_orange] the UI is reachable from the "
                "network and protected by an access token (share the URL below only with "
                "people you trust)."
            )
        else:
            rprint(
                "[bold dark_orange]Warning:[/bold dark_orange] --no-auth: anyone who can reach "
                f"{host}:{port} can read your library and API keys and change your configuration."
            )
        if allowed_hosts_for(host) is None:
            rprint("[dim]Host-header checks are disabled for wildcard bind addresses.[/dim]")

    flask_app = create_app(bind_host=host, access_token=token or None)
    url = f"http://{host}:{port}/" + (f"?token={token}" if token else "")
    if not no_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=[url]).start()

    if debug:
        flask_app.run(host=host, port=port, debug=True)
    else:
        from waitress import create_server

        server = create_server(flask_app, host=host, port=port)
        rprint(f"[green]MOSAIC[/green] running at [link]{url}[/link]  (Ctrl+C to stop)")
        server.run()
