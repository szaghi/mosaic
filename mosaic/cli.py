"""MOSAIC CLI — Multi-source Scientific Article Index and Collector."""
from __future__ import annotations
from pathlib import Path
from typing import Annotated
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

import mosaic.config as cfg_mod
from mosaic.db import Cache
from mosaic.models import SearchFilters
from mosaic.search import search_all
from mosaic.downloader import download as dl_paper
from mosaic.sources import (
    ArxivSource, SemanticScholarSource, ScienceDirectSource,
    DoajSource, EuropePMCSource, OpenAlexSource, BASESource,
)

app = typer.Typer(help="MOSAIC — Multi-source Scientific Article Index and Collector")
console = Console()


def _build_sources(cfg: dict) -> list:
    src_cfg = cfg.get("sources", {})
    sources = []
    if src_cfg.get("arxiv", {}).get("enabled", True):
        sources.append(ArxivSource(delay=cfg.get("rate_limit_delay", 3.0)))
    if src_cfg.get("semantic_scholar", {}).get("enabled", True):
        sources.append(SemanticScholarSource(
            api_key=src_cfg.get("semantic_scholar", {}).get("api_key", "")
        ))
    if src_cfg.get("sciencedirect", {}).get("enabled", True):
        api_key = src_cfg.get("sciencedirect", {}).get("api_key", "")
        if api_key:
            sources.append(ScienceDirectSource(api_key=api_key, open_access_only=True))
    if src_cfg.get("doaj", {}).get("enabled", True):
        sources.append(DoajSource())
    if src_cfg.get("europepmc", {}).get("enabled", True):
        sources.append(EuropePMCSource())
    if src_cfg.get("openalex", {}).get("enabled", True):
        sources.append(OpenAlexSource(email=cfg.get("unpaywall", {}).get("email", "")))
    if src_cfg.get("base", {}).get("enabled", True):
        sources.append(BASESource())
    return sources


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    max_results: Annotated[int, typer.Option("--max", "-n", help="Max results per source")] = 10,
    download: Annotated[bool, typer.Option("--download", "-d", help="Download available PDFs")] = False,
    oa_only: Annotated[bool, typer.Option("--oa-only", help="Show only open access papers")] = False,
    source: Annotated[str, typer.Option("--source", "-s", help="Limit to one source (arxiv, ss, sd, doaj, epmc, oa, base)")] = "",
    year: Annotated[str, typer.Option("--year", "-y", help='Year filter: "2020", "2020-2024", or "2020,2022,2024"')] = "",
    author: Annotated[list[str], typer.Option("--author", "-a", help="Author name filter (repeatable)")] = [],
    journal: Annotated[str, typer.Option("--journal", "-j", help="Journal name filter (substring match)")] = "",
):
    """Search for papers across all configured sources."""
    cfg = cfg_mod.load()
    cache = Cache(cfg["db_path"])
    sources = _build_sources(cfg)

    # filter by source shorthand
    _src_map = {
        "arxiv": "arXiv", "ss": "Semantic Scholar",
        "sd": "ScienceDirect", "doaj": "DOAJ", "epmc": "Europe PMC",
        "oa": "OpenAlex", "base": "BASE",
    }
    if source:
        name = _src_map.get(source.lower(), source)
        sources = [s for s in sources if s.name == name]
        if not sources:
            rprint(f"[red]Unknown source '{source}'. Use: {', '.join(_src_map.keys())}[/red]")
            raise typer.Exit(1)

    # build filters
    filters: SearchFilters | None = None
    if year or author or journal:
        filters = SearchFilters(authors=list(author), journal=journal)
        if year:
            try:
                parsed = SearchFilters.parse_year(year)
                filters.year_from = parsed.year_from
                filters.year_to   = parsed.year_to
                filters.years     = parsed.years
            except ValueError:
                rprint(f'[red]Invalid --year format "{year}". Use: 2020, 2020-2024, or 2020,2022,2024[/red]')
                raise typer.Exit(1)

    errors: list[str] = []
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as prog:
        prog.add_task(f"Searching {len(sources)} source(s) for [bold]{query}[/bold]…")
        papers = search_all(sources, query, max_per_source=max_results, filters=filters, errors=errors)

    for err in errors:
        rprint(f"[yellow]Warning:[/yellow] {err}")

    if oa_only:
        papers = [p for p in papers if p.is_open_access or p.pdf_url]

    if not papers:
        rprint("[yellow]No results found.[/yellow]")
        raise typer.Exit()

    # save to cache
    for p in papers:
        cache.save(p)

    _print_results(papers)

    if download:
        _download_all(papers, cfg, cache)


@app.command()
def get(
    doi: Annotated[str, typer.Argument(help="DOI of the paper to download")],
):
    """Download a paper by DOI (uses Unpaywall if no direct PDF known)."""
    cfg = cfg_mod.load()
    cache = Cache(cfg["db_path"])
    from mosaic.models import Paper
    paper = Paper(title=doi, doi=doi, source="manual")
    path = dl_paper(paper, cfg["download_dir"], cache, cfg.get("unpaywall", {}).get("email", ""))
    if path:
        rprint(f"[green]Saved:[/green] {path}")
    else:
        rprint("[red]Could not find a downloadable PDF for this DOI.[/red]")


@app.command()
def config(
    show: Annotated[bool, typer.Option("--show", help="Print current config")] = False,
    elsevier_key: Annotated[str, typer.Option(help="Set Elsevier API key")] = "",
    ss_key: Annotated[str, typer.Option(help="Set Semantic Scholar API key")] = "",
    unpaywall_email: Annotated[str, typer.Option(help="Set Unpaywall email")] = "",
    download_dir: Annotated[str, typer.Option(help="Set download directory")] = "",
):
    """View or update MOSAIC configuration."""
    cfg = cfg_mod.load()

    if elsevier_key:
        cfg["sources"]["sciencedirect"]["api_key"] = elsevier_key
    if ss_key:
        cfg["sources"]["semantic_scholar"]["api_key"] = ss_key
    if unpaywall_email:
        cfg["unpaywall"]["email"] = unpaywall_email
    if download_dir:
        cfg["download_dir"] = download_dir

    if any([elsevier_key, ss_key, unpaywall_email, download_dir]):
        cfg_mod.save(cfg)
        rprint(f"[green]Config saved to[/green] ~/.config/mosaic/config.toml")

    if show or not any([elsevier_key, ss_key, unpaywall_email, download_dir]):
        import tomli_w
        console.print_json(data=cfg)


def _print_results(papers: list) -> None:
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", min_width=30, ratio=3)
    table.add_column("Authors", ratio=2)
    table.add_column("Year", width=6)
    table.add_column("Source", width=16)
    table.add_column("OA", width=4)
    table.add_column("PDF", width=5)

    for i, p in enumerate(papers, 1):
        oa = "[green]yes[/green]" if p.is_open_access else "[red]no[/red]"
        pdf = "[green]✓[/green]" if p.pdf_url else "[dim]–[/dim]"
        table.add_row(str(i), p.title[:80], p.short_authors, str(p.year or ""), p.source, oa, pdf)

    console.print(table)
    console.print(f"[dim]{len(papers)} result(s)[/dim]")


def _download_all(papers: list, cfg: dict, cache: Cache) -> None:
    email = cfg.get("unpaywall", {}).get("email", "")
    download_dir = cfg["download_dir"]
    ok = fail = skip = 0

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=False) as prog:
        for p in papers:
            if not (p.pdf_url or p.doi):
                skip += 1
                continue
            task = prog.add_task(f"Downloading: {p.title[:50]}…")
            path = dl_paper(p, download_dir, cache, email)
            prog.remove_task(task)
            if path:
                ok += 1
                rprint(f"  [green]✓[/green] {Path(path).name}")
            else:
                fail += 1
                rprint(f"  [red]✗[/red] {p.title[:60]}")

    console.print(f"\n[bold]Done:[/bold] {ok} downloaded, {fail} failed, {skip} skipped (no PDF)")


if __name__ == "__main__":
    app()
