"""``mosaic cache`` — inspect and manage the local SQLite cache."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich import print as rprint
from rich.table import Table

import mosaic.config as cfg_mod
from mosaic.cli.app import cache_app, console
from mosaic.cli.helpers import RAINBOW, open_cache

# ── mosaic cache subcommands ──────────────────────────────────────────────────


def _cache_and_cfg():
    cfg = cfg_mod.load()
    return open_cache(cfg), cfg


@cache_app.command("stats")
def cache_stats() -> None:
    """Print a summary of the local cache."""
    cache, _ = _cache_and_cfg()
    s = cache.stats()
    mb = s["db_bytes"] / 1_048_576

    table = Table(show_header=False, box=box.SIMPLE, show_edge=False)
    table.add_column("Key", style="dim", min_width=20)
    table.add_column("Value", justify="right")
    table.add_row("Papers cached", f"[cyan]{s['papers']}[/cyan]")
    table.add_row("  with abstract", f"[dim]{s['with_abstract']}[/dim]")
    table.add_row("  open access", f"[dim]{s['open_access']}[/dim]")
    table.add_row("  with PDF URL", f"[dim]{s['with_pdf_url']}[/dim]")
    table.add_row("Downloads (ok)", f"[green]{s['downloaded']}[/green]")
    table.add_row("Searches logged", f"[cyan]{s['searches']}[/cyan]")
    table.add_row("Exports tracked", f"[cyan]{s['exports']}[/cyan]")
    table.add_row("DB size", f"[dim]{mb:.2f} MB[/dim]")
    console.print(table)


@cache_app.command("list")
def cache_list(
    query: Annotated[str, typer.Option("--query", "-q", help="Filter by title/abstract")] = "",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max rows to show")] = 50,
    offset: Annotated[int, typer.Option("--offset", help="Skip first N rows")] = 0,
) -> None:
    """List cached papers, newest first."""
    cache, _ = _cache_and_cfg()
    papers = cache.list_papers(limit=limit, offset=offset, query=query)
    total = cache.count_papers(query=query)

    if not papers:
        rprint("[dim]No papers in cache.[/dim]")
        return

    table = Table(
        show_header=True, header_style="cyan", box=box.SIMPLE, show_edge=False, expand=True
    )
    table.add_column("#", width=5)
    table.add_column("Title", min_width=30, ratio=3)
    table.add_column("Authors", ratio=2)
    table.add_column("Year", width=6)
    table.add_column("Source", width=16)
    table.add_column("OA", width=4)
    table.add_column("PDF", width=4)
    table.add_column("Abstr", width=5)

    for i, p in enumerate(papers, offset + 1):
        color = RAINBOW[(i - 1) % len(RAINBOW)]
        oa = "[green]✓[/green]" if p.is_open_access else "[red]✗[/red]"
        pdf = "[green]✓[/green]" if p.pdf_url else "[dim]–[/dim]"
        abstract = "[green]✓[/green]" if p.abstract else "[dim]–[/dim]"
        table.add_row(
            f"[{color}]{i}[/{color}]",
            p.title[:80],
            p.short_authors,
            str(p.year or ""),
            p.source,
            oa,
            pdf,
            abstract,
        )

    console.print(table)
    showing = offset + len(papers)
    console.print(f"[dim]Showing {offset + 1}–{showing} of {total}[/dim]")


@cache_app.command("show")
def cache_show(
    identifier: Annotated[str, typer.Argument(help="DOI, arXiv ID, or full UID of the paper")],
) -> None:
    """Show full cached metadata for a paper."""
    from mosaic.models import Paper as _Paper

    cache, _ = _cache_and_cfg()

    # Try as-is (full UID), then as DOI, then as arXiv ID
    paper = cache.get_by_uid(identifier)
    if paper is None:
        stub = _Paper(title=identifier, doi=identifier, source="")
        paper = cache.get_by_uid(stub.uid)
    if paper is None:
        stub2 = _Paper(title=identifier, arxiv_id=identifier, source="")
        paper = cache.get_by_uid(stub2.uid)
    if paper is None:
        rprint(f"[red]Not found in cache:[/red] {identifier}")
        raise typer.Exit(1)

    dl = cache.get_download(paper.uid)

    table = Table(show_header=False, box=box.SIMPLE, show_edge=False, expand=True)
    table.add_column("Field", style="dim", min_width=18)
    table.add_column("Value")

    def row(k, v):
        table.add_row(k, str(v) if v is not None else "[dim]–[/dim]")

    row("Title", paper.title)
    row("Authors", paper.short_authors)
    row("Year", paper.year)
    row("DOI", paper.doi)
    row("arXiv ID", paper.arxiv_id)
    row("Journal", paper.journal)
    row("Source", paper.source)
    row("Open access", "[green]yes[/green]" if paper.is_open_access else "no")
    row("PDF URL", paper.pdf_url)
    row("Citation count", paper.citation_count)
    row("UID", paper.uid)
    if paper.abstract:
        row("Abstract", paper.abstract[:300] + ("…" if len(paper.abstract) > 300 else ""))
    if dl:
        table.add_section()
        row("Local file", dl["local_path"])
        row("Download status", dl["status"])
        row("Downloaded at", dl["downloaded_at"])

    console.print(table)


@cache_app.command("verify")
def cache_verify() -> None:
    """Check that all tracked download files still exist on disk."""
    cache, _ = _cache_and_cfg()
    results = cache.verify_downloads()

    if not results:
        rprint("[dim]No completed downloads tracked.[/dim]")
        return

    ok = [r for r in results if r["exists"]]
    missing = [r for r in results if not r["exists"]]

    rprint(f"[green]{len(ok)} file(s) OK[/green], [red]{len(missing)} missing[/red]")

    if missing:
        table = Table(show_header=True, header_style="cyan", box=box.SIMPLE, show_edge=False)
        table.add_column("UID", style="dim")
        table.add_column("Missing path")
        for r in missing:
            table.add_row(r["uid"], r["local_path"] or "[dim]–[/dim]")
        console.print(table)
        rprint("[dim]Run [bold]mosaic cache clean[/bold] to remove stale records.[/dim]")


@cache_app.command("clean")
def cache_clean() -> None:
    """Remove download records for files that no longer exist on disk."""
    cache, _ = _cache_and_cfg()
    removed = cache.clean_stubs()
    if removed:
        rprint(f"[green]Removed {removed} stale download record(s).[/green]")
    else:
        rprint("[dim]Nothing to clean — all tracked files are present.[/dim]")


@cache_app.command("clear")
def cache_clear(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")] = False,
) -> None:
    """Wipe the entire cache (papers, downloads, searches, exports)."""
    cache, _ = _cache_and_cfg()
    s = cache.stats()
    if not yes:
        rprint(
            f"[bold red]This will permanently delete {s['papers']} paper(s), "
            f"{s['downloaded']} download record(s), and {s['searches']} search(es).[/bold red]"
        )
        typer.confirm("Continue?", abort=True)
    cache.clear()
    rprint("[green]Cache cleared.[/green]")


@cache_app.command("export")
def cache_export(
    output: Annotated[
        Path, typer.Argument(help="Output file (.md, .markdown, .csv, .json, .bib, .ris)")
    ],
    query: Annotated[str, typer.Option("--query", "-q", help="Filter by title/abstract")] = "",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max papers to export (0 = all)")] = 0,
) -> None:
    """Bulk export cached papers to a file."""
    from mosaic.exporter import export

    cache, _ = _cache_and_cfg()
    papers = cache.list_papers(limit=limit or 999_999, query=query)

    if not papers:
        rprint("[dark_orange]No papers to export.[/dark_orange]")
        raise typer.Exit()

    try:
        export(papers, output)
        rprint(f"[green]Exported {len(papers)} paper(s) to[/green] {output}")
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
