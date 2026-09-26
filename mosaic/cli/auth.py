"""``mosaic auth`` — browser sessions for authenticated PDF access."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich import box
from rich import print as rprint
from rich.table import Table

from mosaic.cli.app import auth_app, console

_AUTH_PROVIDERS = ["elsevier", "springer", "scopus"]


def _complete_session_names() -> list[str]:
    from mosaic.auth import list_sessions

    return [s["name"] for s in list_sessions()]


@auth_app.command("login")
def auth_login(
    name: Annotated[
        str,
        typer.Argument(
            help="Session name, e.g. elsevier, springer, myuni",
            autocompletion=lambda: _AUTH_PROVIDERS,
        ),
    ],
    url: Annotated[str, typer.Option("--url", "-u", help="URL to open in the browser for login")],
) -> None:
    """Open a browser, log in to a site, and save the session for future PDF downloads."""

    from mosaic.auth import login as do_login

    try:
        asyncio.run(do_login(name, url))
    except ImportError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


@auth_app.command("logout")
def auth_logout(
    name: Annotated[
        str,
        typer.Argument(
            help="Session name to remove",
            autocompletion=_complete_session_names,
        ),
    ],
) -> None:
    """Remove a saved browser session."""
    from mosaic.auth import delete_session

    if delete_session(name):
        rprint(f"[green]Session removed:[/green] {name}")
    else:
        rprint(f"[dark_orange]No session found for:[/dark_orange] {name}")
        raise typer.Exit(1)


@auth_app.command("status")
def auth_status() -> None:
    """List all saved browser sessions."""
    from mosaic.auth import list_sessions

    sessions = list_sessions()
    if not sessions:
        rprint(
            "[dim]No saved sessions. Use [bold]mosaic auth login <name> --url <url>[/bold] to add one.[/dim]"
        )
        return
    table = Table(show_header=True, header_style="cyan", box=box.SIMPLE, show_edge=False)
    table.add_column("Name", style="bold")
    table.add_column("Domain")
    table.add_column("Saved")
    table.add_column("Valid")
    table.add_column("Path", style="dim")
    for s in sessions:
        valid_cell = "[green]✓[/green]" if s["valid"] else "[red]✗ expired[/red]"
        table.add_row(s["name"], s["domain"], s["saved"], valid_cell, s["path"])
    console.print(table)
