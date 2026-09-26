"""``mosaic notebook`` — Google NotebookLM integration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn

import mosaic.config as cfg_mod
from mosaic.cli.app import notebook_app, warn
from mosaic.cli.helpers import FIELD_VALUES, open_cache
from mosaic.db import Cache
from mosaic.search import search_all
from mosaic.services import FIELD_CHOICES, build_filters, filter_papers
from mosaic.source_registry import build_sources


@notebook_app.command("create")
def notebook_create(
    name: Annotated[str, typer.Argument(help="Notebook name")],
    query: Annotated[
        str, typer.Option("--query", "-q", help="Search query to populate the notebook")
    ] = "",
    from_dir: Annotated[
        Path | None, typer.Option("--from-dir", help="Import all PDFs from this directory")
    ] = None,
    max_results: Annotated[int, typer.Option("--max", "-n", help="Max results per source")] = 10,
    oa_only: Annotated[
        bool, typer.Option("--oa-only", help="Only include open-access papers")
    ] = False,
    pdf_only: Annotated[
        bool, typer.Option("--pdf-only", help="Only include papers with a downloadable PDF")
    ] = False,
    podcast: Annotated[
        bool, typer.Option("--podcast", help="Queue an Audio Overview after import")
    ] = False,
    video: Annotated[
        bool, typer.Option("--video", help="Queue a Video Overview after import")
    ] = False,
    briefing: Annotated[
        bool, typer.Option("--briefing", help="Queue a Briefing Doc after import")
    ] = False,
    study_guide: Annotated[
        bool, typer.Option("--study-guide", help="Queue a Study Guide after import")
    ] = False,
    quiz: Annotated[bool, typer.Option("--quiz", help="Queue a Quiz after import")] = False,
    flashcards: Annotated[
        bool, typer.Option("--flashcards", help="Queue Flashcards after import")
    ] = False,
    infographic: Annotated[
        bool, typer.Option("--infographic", help="Queue an Infographic after import")
    ] = False,
    slide_deck: Annotated[
        bool, typer.Option("--slide-deck", help="Queue a Slide Deck after import")
    ] = False,
    data_table: Annotated[
        bool, typer.Option("--data-table", help="Queue a Data Table after import")
    ] = False,
    mind_map: Annotated[
        bool, typer.Option("--mind-map", help="Queue a Mind Map after import")
    ] = False,
    year: Annotated[
        str,
        typer.Option("--year", "-y", help='Year filter: "2020", "2020-2024", or "2020,2022,2024"'),
    ] = "",
    author: Annotated[
        list[str], typer.Option("--author", "-a", help="Author name filter (repeatable)")
    ] = [],
    journal: Annotated[
        str, typer.Option("--journal", "-j", help="Journal name filter (substring match)")
    ] = "",
    field: Annotated[
        str,
        typer.Option(
            "--field",
            "-f",
            help='Scope query to "title", "abstract", or "all" (default)',
            autocompletion=lambda: FIELD_VALUES,
        ),
    ] = "all",
    raw_query: Annotated[
        str,
        typer.Option(
            "--raw-query",
            help="Raw query sent directly to source APIs, bypassing all field transforms",
        ),
    ] = "",
    download_dir: Annotated[
        str, typer.Option("--download-dir", help="Override PDF download directory for this run")
    ] = "",
):
    """Create a NotebookLM notebook from a search query or a directory of PDFs.

    Requires: pip install 'mosaic-search[notebooklm]' && notebooklm login
    """
    from mosaic.notebooklm_bridge import (
        create_notebook,
        create_notebook_from_dir,
        describe_error,
        preflight_error,
    )

    problem = preflight_error()
    if problem:
        rprint(f"[red]{problem}[/red]")
        raise typer.Exit(1)

    if from_dir and query:
        rprint("[red]Use either --query or --from-dir, not both.[/red]")
        raise typer.Exit(1)
    if not from_dir and not query:
        rprint("[red]Provide --query or --from-dir.[/red]")
        raise typer.Exit(1)

    cfg = cfg_mod.load()
    if download_dir:
        cfg["download_dir"] = download_dir

    # collect requested artifacts
    _artifact_flags = {
        "podcast": podcast,
        "video": video,
        "briefing": briefing,
        "study_guide": study_guide,
        "quiz": quiz,
        "flashcards": flashcards,
        "infographic": infographic,
        "slide_deck": slide_deck,
        "data_table": data_table,
        "mind_map": mind_map,
    }
    _artifacts = {name for name, enabled in _artifact_flags.items() if enabled}

    # ── from-dir path ─────────────────────────────────────────────────────────
    if from_dir:
        from_dir = Path(from_dir)
        if not from_dir.is_dir():
            rprint(f"[red]Directory not found: {from_dir}[/red]")
            raise typer.Exit(1)
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
        ) as prog:
            prog.add_task(f"Creating notebook [bold]{name}[/bold] from {from_dir}…")
            try:
                nb_result = asyncio.run(
                    create_notebook_from_dir(name, from_dir, artifacts=_artifacts)
                )
            except ValueError as e:
                rprint(f"[red]{e}[/red]")
                raise typer.Exit(1) from None
            except Exception as e:
                rprint(f"[red]{describe_error(e)}[/red]")
                raise typer.Exit(1) from None
        _print_notebook_result(nb_result)
        return

    # ── query path: search → download → import ────────────────────────────────
    sources = build_sources(cfg)
    cache = open_cache(cfg)

    if field not in FIELD_CHOICES:
        rprint('[red]--field must be "title", "abstract", or "all"[/red]')
        raise typer.Exit(1)

    filters, year_warning = build_filters(
        year=year, author=list(author), journal=journal, field=field, raw_query=raw_query
    )
    if year_warning:
        rprint(f"[red]{year_warning}[/red]")
        raise typer.Exit(1)

    errors: list[str] = []
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        prog.add_task(f"Searching {len(sources)} source(s) for [bold]{query}[/bold]…")
        papers = search_all(
            sources, query, max_per_source=max_results, filters=filters, errors=errors
        )

    for err in errors:
        warn(f"[dark_orange]Warning:[/dark_orange] {err}")

    papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only)

    if not papers:
        rprint("[dark_orange]No results found.[/dark_orange]")
        raise typer.Exit()

    rprint(f"[dim]Found {len(papers)} paper(s). Downloading PDFs…[/dim]")

    papers_with_paths = _download_each(papers, cfg, cache)

    downloaded = sum(1 for _, path in papers_with_paths if path)
    rprint(
        f"[dim]{downloaded} PDF(s) downloaded, {len(papers) - downloaded} fallback to URL.[/dim]"
    )

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        prog.add_task(f"Importing into NotebookLM notebook [bold]{name}[/bold]…")
        try:
            nb_result = asyncio.run(create_notebook(name, papers_with_paths, artifacts=_artifacts))
        except Exception as e:
            rprint(f"[red]{describe_error(e)}[/red]")
            raise typer.Exit(1) from None

    _print_notebook_result(nb_result)


def _download_each(papers: list, cfg: dict, cache: Cache) -> list[tuple]:
    """Attempt a download for every paper (with a spinner) → ``[(paper, Path | None)]``."""
    from mosaic.workflows import download_papers

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        task_ids: list = []

        def _start(paper) -> None:
            task_ids.append(prog.add_task(f"{paper.title[:55]}…"))

        def _done(_item) -> None:
            prog.remove_task(task_ids.pop())

        report = download_papers(
            papers, cfg, cache, skip_without_link=False, on_start=_start, on_item=_done
        )
    return [(i.paper, Path(i.path) if i.path else None) for i in report.items]


def _print_notebook_result(nb_result) -> None:
    rprint(f"[green]Notebook created:[/green] {nb_result.url}")
    rprint(f"[dim]{nb_result.sources_added} source(s) added.[/dim]")
    if nb_result.artifacts_queued:
        rprint(
            f"[dim]{', '.join(nb_result.artifacts_queued)} queued — "
            "check NotebookLM in a few minutes.[/dim]"
        )
    for warning in nb_result.warnings():
        rprint(f"[dark_orange]{warning}[/dark_orange]")
