"""Typer application objects, global options and console output."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console

from mosaic.errors import MosaicError, set_verbose_logging


def _version_callback(value: bool) -> None:
    if value:
        from mosaic import __version__

        rprint(f"mosaic {__version__}")
        raise typer.Exit()


class _MosaicTyper(typer.Typer):
    """Typer app that reports MOSAIC errors (e.g. an unreadable config) without a traceback."""

    def __call__(self, *args, **kwargs):
        try:
            return super().__call__(*args, **kwargs)
        except MosaicError as e:
            rprint(f"[red]{e}[/red]")
            raise SystemExit(1) from None


app = _MosaicTyper(help="MOSAIC — Multi-source Scientific Article Indexer and Collector")
notebook_app = typer.Typer(
    help="Create and populate Google NotebookLM notebooks from search results."
)
auth_app = typer.Typer(help="Manage browser sessions for authenticated PDF access.")
cache_app = typer.Typer(help="Inspect and manage the local SQLite cache.")
skill_app = typer.Typer(help="Manage the bundled MOSAIC Claude Code skill.")
app.add_typer(notebook_app, name="notebook")
app.add_typer(auth_app, name="auth")
app.add_typer(cache_app, name="cache")
app.add_typer(skill_app, name="skill")


_verbose: bool = False


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Show warnings and per-source stats"),
    ] = False,
) -> None:
    global _verbose
    _verbose = verbose
    set_verbose_logging(verbose)

    from mosaic.cli.helpers import close_open_caches

    # Commands open the cache through helpers.open_cache(); close it when done
    ctx.call_on_close(close_open_caches)


console = Console()
err_console = Console(stderr=True)


def warn(msg: str) -> None:
    """Print a warning — only when --verbose is active."""
    if _verbose:
        rprint(msg)
