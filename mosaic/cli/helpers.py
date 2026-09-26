"""Helpers shared by several CLI commands (result display, exports, pushes)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich import box
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from mosaic.cli.app import console, err_console
from mosaic.db import Cache
from mosaic.services import select_cached_papers
from mosaic.workflows import auto_index, finalize_search

_open_caches: list[Cache] = []


def open_cache(cfg: dict) -> Cache:
    """Open the configured cache; it is closed when the current command ends."""
    cache = Cache(cfg["db_path"])
    _open_caches.append(cache)
    return cache


def close_open_caches() -> None:
    """Close every cache opened with :func:`open_cache` (called by the app callback)."""
    while _open_caches:
        _open_caches.pop().close()


def run_auto_index(papers: list, cfg: dict, cache: Cache) -> None:
    """Run ``rag.auto_index`` and report (never hide) a failure."""
    warning = auto_index(papers, cfg, cache)
    if warning:
        rprint(f"[dark_orange]{warning}[/dark_orange]")


def read_dois_or_exit(path: Path) -> list[str]:
    from mosaic.bulk import read_dois

    if not path.exists():
        rprint(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)
    try:
        return read_dois(path)
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


def select_papers_or_exit(
    cache: Cache, *, query: str = "", from_file: Path | None = None, year: str = ""
):
    """Cached papers selected by --query/--from/--year (``None`` = whole library)."""
    dois = read_dois_or_exit(from_file) if from_file else None
    try:
        return select_cached_papers(cache, query=query, dois=dois, year=year or "")
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


def export_outputs(papers: list, output: list[Path], *, quiet: bool = False) -> None:
    """Write *papers* to every ``--output`` path (errors go to stderr in quiet/JSON mode)."""
    if not output:
        return
    from mosaic.exporter import export

    for path in output:
        try:
            export(papers, path)
        except ValueError as e:
            (err_console if quiet else console).print(f"[red]{e}[/red]")
            raise typer.Exit(1) from None
        if not quiet:
            rprint(f"[green]Saved:[/green] {path}")


def finish_results(
    papers: list,
    cfg: dict,
    cache: Cache,
    *,
    query: str = "",
    output: list[Path] | None = None,
    do_download: bool = False,
    sort_by: str = "",
    oa_only: bool = False,
    pdf_only: bool = False,
    zotero: bool = False,
    zotero_collection: str = "",
    zotero_local: bool = False,
    obsidian: bool = False,
    obsidian_folder: str = "",
    show_score: bool = False,
    prefer_cache: bool = False,
    save: bool = True,
    history: dict | None = None,
) -> None:
    """Shared post-processing: filter, export, download, push to Zotero/Obsidian."""
    try:
        papers = finalize_search(
            papers,
            cfg,
            cache,
            query=query,
            oa_only=oa_only,
            pdf_only=pdf_only,
            sort_by=sort_by,
            prefer_cache=prefer_cache,
            save=save,
            history=history,
        )
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if not papers:
        rprint("[dark_orange]No results found.[/dark_orange]")
        raise typer.Exit()

    show_rel = sort_by == "relevance" or show_score
    score_label = "Sim." if show_score else "Rel."
    print_results(papers, show_relevance=show_rel, score_label=score_label)

    export_outputs(papers, output or [])

    pdf_map: dict[str, str] = {}
    if do_download:
        pdf_map = download_all(papers, cfg, cache)

    if zotero:
        push_zotero(
            papers,
            cfg,
            collection_name=zotero_collection,
            force_local=zotero_local,
            pdf_map=pdf_map,
        )

    if obsidian:
        push_obsidian(papers, cfg, subfolder_override=obsidian_folder)

    # Auto-index last, so freshly downloaded PDFs are indexed as full text
    run_auto_index(papers, cfg, cache)


RAINBOW = ["red", "dark_orange", "green", "cyan", "blue", "magenta"]

SORT_VALUES = ["citations", "year", "relevance"]
FIELD_VALUES = ["title", "abstract", "all"]


def print_results(papers: list, show_relevance: bool = False, score_label: str = "Rel.") -> None:
    show_citations = any(p.citation_count is not None for p in papers)

    table = Table(
        show_header=True,
        header_style="cyan",
        box=box.SIMPLE,
        show_edge=False,
        expand=True,
    )
    table.add_column("#", width=3)
    table.add_column("Title", min_width=30, ratio=3)
    table.add_column("Authors", ratio=2)
    table.add_column("Year", width=6)
    table.add_column("DOI", min_width=20, overflow="fold")
    table.add_column("Source", width=16)
    table.add_column("OA", width=4)
    table.add_column("PDF", width=5)
    if show_citations:
        table.add_column("Cited", width=7, justify="right")
    if show_relevance:
        table.add_column(score_label, width=6, justify="right")

    for i, p in enumerate(papers, 1):
        oa = "[green]yes[/green]" if p.is_open_access else "[red]no[/red]"
        pdf = "[green]✓[/green]" if p.pdf_url else "[dim]–[/dim]"
        doi = p.doi or "[dim]–[/dim]"
        color = RAINBOW[(i - 1) % len(RAINBOW)]
        src_color = RAINBOW[hash(p.source) % len(RAINBOW)]
        source = f"[{src_color}]{p.source}[/{src_color}]"
        row = [
            f"[{color}]{i}[/{color}]",
            p.title[:80],
            p.short_authors,
            str(p.year or ""),
            doi,
            source,
            oa,
            pdf,
        ]
        if show_citations:
            cited = str(p.citation_count) if p.citation_count is not None else "[dim]–[/dim]"
            row.append(cited)
        if show_relevance:
            rel = f"{p.relevance_score:.2f}" if p.relevance_score is not None else "[dim]–[/dim]"
            row.append(rel)
        table.add_row(*row)

    console.print(table)
    console.print(f"[dim]{len(papers)} result(s)[/dim]")


def download_all(papers: list, cfg: dict, cache: Cache) -> dict[str, str]:
    """Download PDFs for *papers*. Returns a ``{paper.uid: local_path}`` map."""
    from mosaic.workflows import download_papers

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=False
    ) as prog:
        task_ids: list = []

        def _start(paper) -> None:
            task_ids.append(prog.add_task(f"Downloading: {paper.title[:50]}…"))

        def _done(item) -> None:
            if item.status == "skip":
                return
            prog.remove_task(task_ids.pop())
            if item.status == "ok":
                rprint(f"  [green]✓[/green] {Path(item.path).name}")
            else:
                rprint(f"  [red]✗[/red] {item.paper.title[:60]}")

        report = download_papers(papers, cfg, cache, on_start=_start, on_item=_done)

    console.print(
        f"\n[bold]Done:[/bold] {report.count('ok')} downloaded, {report.count('fail')} failed, "
        f"{report.count('skip')} skipped (no PDF)"
    )
    return report.pdf_map


def push_zotero(
    papers: list,
    cfg: dict,
    *,
    collection_name: str = "",
    force_local: bool = False,
    pdf_map: dict[str, str] | None = None,
) -> None:
    """Export *papers* to Zotero (local or web API)."""
    from mosaic.workflows import push_to_zotero

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        prog.add_task(f"Adding {len(papers)} paper(s) to Zotero…")
        result = push_to_zotero(
            papers,
            cfg,
            collection_name=collection_name,
            force_local=force_local,
            pdf_map=pdf_map,
        )

    if not result["ok"]:
        rprint(f"[red]{result['msg']}[/red]")
        raise typer.Exit(1)

    rprint(f"[green]Zotero:[/green] {result['msg']}")
    if result.get("attached"):
        rprint(f"[dim]{result['attached']} PDF(s) linked.[/dim]")


def push_obsidian(
    papers: list,
    cfg: dict,
    *,
    subfolder_override: str = "",
) -> None:
    """Export *papers* as Obsidian notes to the configured vault."""
    from mosaic.workflows import push_to_obsidian

    result = push_to_obsidian(papers, cfg, subfolder_override=subfolder_override)
    if not result["ok"]:
        rprint(f"[red]{result['msg']}[/red]")
        raise typer.Exit(1)

    rprint(f"[green]Obsidian:[/green] {result['msg']}")
