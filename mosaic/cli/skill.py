"""``mosaic skill`` — install or print the bundled Claude Code skill."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint

from mosaic.cli.app import skill_app

# ---------------------------------------------------------------------------
# Skill subcommand
# ---------------------------------------------------------------------------


@skill_app.command("install")
def skill_install(
    global_: Annotated[
        bool,
        typer.Option("--global", help="Install to ~/.claude/skills/ (available from all projects)"),
    ] = False,
) -> None:
    """Install the bundled MOSAIC Claude Code skill.

    By default installs to ./.claude/skills/mosaic/ in the current directory,
    making /mosaic available as a Claude Code slash command for that project.
    Use --global to install to ~/.claude/skills/mosaic/ for all projects.
    """
    import importlib.resources as _res

    try:
        skill_text = (_res.files("mosaic.data") / "SKILL.md").read_text(encoding="utf-8")
    except Exception as e:
        rprint(f"[red]Could not read bundled skill: {e}[/red]")
        raise typer.Exit(1) from None

    target = (Path.home() if global_ else Path(".")) / ".claude" / "skills" / "mosaic" / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(skill_text, encoding="utf-8")
    rprint(f"[green]Skill installed to[/green] {target.resolve()}")
    rprint("[dim]Open a new Claude Code session to load the skill, then use /mosaic.[/dim]")


@skill_app.command("show")
def skill_show() -> None:
    """Print the bundled MOSAIC Claude Code skill content to stdout."""
    import importlib.resources as _res

    try:
        skill_text = (_res.files("mosaic.data") / "SKILL.md").read_text(encoding="utf-8")
        print(skill_text)
    except Exception as e:
        rprint(f"[red]Could not read bundled skill: {e}[/red]")
        raise typer.Exit(1) from None
