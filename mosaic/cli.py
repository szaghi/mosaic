"""MOSAIC CLI — Multi-source Scientific Article Indexer and Collector."""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Annotated, Optional
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
    ScienceDirectBrowserSource, SpringerBrowserSource,
    DoajSource, EuropePMCSource, OpenAlexSource, BASESource, CORESource,
    NASAADSSource, IEEEXploreSource, ZenodoSource, CrossrefSource,
    SpringerAPISource, CustomSource,
)

def _version_callback(value: bool) -> None:
    if value:
        from mosaic import __version__
        rprint(f"mosaic {__version__}")
        raise typer.Exit()


app = typer.Typer(help="MOSAIC — Multi-source Scientific Article Indexer and Collector")
notebook_app = typer.Typer(help="Create and populate Google NotebookLM notebooks from search results.")
auth_app = typer.Typer(help="Manage browser sessions for authenticated PDF access.")
app.add_typer(notebook_app, name="notebook")
app.add_typer(auth_app, name="auth")


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", callback=_version_callback, is_eager=True, help="Show version and exit"),
    ] = False,
) -> None:
    pass
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
        else:
            browser_src = ScienceDirectBrowserSource()
            if browser_src.available():
                sources.append(browser_src)
    if src_cfg.get("doaj", {}).get("enabled", True):
        sources.append(DoajSource())
    if src_cfg.get("europepmc", {}).get("enabled", True):
        sources.append(EuropePMCSource())
    if src_cfg.get("openalex", {}).get("enabled", True):
        sources.append(OpenAlexSource(email=cfg.get("unpaywall", {}).get("email", "")))
    if src_cfg.get("base", {}).get("enabled", True):
        sources.append(BASESource())
    if src_cfg.get("core", {}).get("enabled", True):
        sources.append(CORESource(api_key=src_cfg.get("core", {}).get("api_key", "")))
    if src_cfg.get("nasa_ads", {}).get("enabled", True):
        sources.append(NASAADSSource(api_key=src_cfg.get("nasa_ads", {}).get("api_key", "")))
    if src_cfg.get("ieee", {}).get("enabled", True):
        sources.append(IEEEXploreSource(api_key=src_cfg.get("ieee", {}).get("api_key", "")))
    if src_cfg.get("zenodo", {}).get("enabled", True):
        sources.append(ZenodoSource(api_key=src_cfg.get("zenodo", {}).get("api_key", "")))
    if src_cfg.get("crossref", {}).get("enabled", True):
        sources.append(CrossrefSource(email=cfg.get("unpaywall", {}).get("email", "")))
    if src_cfg.get("springer_api", {}).get("enabled", True):
        sources.append(SpringerAPISource(api_key=src_cfg.get("springer_api", {}).get("api_key", "")))
    if src_cfg.get("springer", {}).get("enabled", True):
        springer_src = SpringerBrowserSource()
        if springer_src.available():
            sources.append(springer_src)
    for custom_cfg in cfg.get("custom_sources", []):
        if custom_cfg.get("enabled", True):
            sources.append(CustomSource(custom_cfg))
    return sources


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    max_results: Annotated[int, typer.Option("--max", "-n", help="Max results per source")] = 10,
    download: Annotated[bool, typer.Option("--download", "-d", help="Download available PDFs")] = False,
    oa_only: Annotated[bool, typer.Option("--oa-only", help="Show only open access papers")] = False,
    pdf_only: Annotated[bool, typer.Option("--pdf-only", help="Show only papers with a downloadable PDF")] = False,
    source: Annotated[str, typer.Option("--source", "-s", help="Limit to one source (arxiv, ss, sd, sp, springer, doaj, epmc, oa, base, core, ads, ieee, zenodo, crossref)")] = "",
    year: Annotated[str, typer.Option("--year", "-y", help='Year filter: "2020", "2020-2024", or "2020,2022,2024"')] = "",
    author: Annotated[list[str], typer.Option("--author", "-a", help="Author name filter (repeatable)")] = [],
    journal: Annotated[str, typer.Option("--journal", "-j", help="Journal name filter (substring match)")] = "",
    field: Annotated[str, typer.Option("--field", "-f", help='Scope query to "title", "abstract", or "all" (default)')] = "all",
    raw_query: Annotated[str, typer.Option("--raw-query", help="Raw query sent directly to source APIs, bypassing all field transforms")] = "",
    output: Annotated[list[Path], typer.Option("--output", "-o", help="Save results to file (.md, .markdown, .csv, .json, .bib); repeatable")] = [],
    download_dir: Annotated[str, typer.Option("--download-dir", help="Override PDF download directory for this run")] = "",
):
    """Search for papers across all configured sources."""
    cfg = cfg_mod.load()
    if download_dir:
        cfg["download_dir"] = download_dir
    cache = Cache(cfg["db_path"])
    sources = _build_sources(cfg)

    # filter by source shorthand
    _src_map = {
        "arxiv": "arXiv", "ss": "Semantic Scholar",
        "sd": "ScienceDirect", "doaj": "DOAJ", "epmc": "Europe PMC",
        "oa": "OpenAlex", "base": "BASE", "core": "CORE",
        "sp": "Springer", "springer": "Springer Nature",
        "ads": "NASA ADS", "ieee": "IEEE Xplore",
        "zenodo": "Zenodo", "crossref": "Crossref",
    }
    if source:
        key = source.lower()
        if key not in _src_map:
            rprint(f"[red]Unknown source '{source}'. Use: {', '.join(_src_map.keys())}[/red]")
            raise typer.Exit(1)
        name = _src_map[key]
        sources = [s for s in sources if s.name == name]
        if not sources:
            rprint(f"[yellow]Source '{source}' is not active (missing API key or disabled in config).[/yellow]")
            raise typer.Exit(1)

    if field not in ("all", "title", "abstract"):
        rprint('[red]--field must be "title", "abstract", or "all"[/red]')
        raise typer.Exit(1)

    # build filters
    filters: SearchFilters | None = None
    if year or author or journal or field != "all" or raw_query:
        filters = SearchFilters(authors=list(author), journal=journal, field=field, raw_query=raw_query)
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
    if pdf_only:
        papers = [p for p in papers if p.pdf_url]

    if not papers:
        rprint("[yellow]No results found.[/yellow]")
        raise typer.Exit()

    # save to cache
    for p in papers:
        cache.save(p)

    _print_results(papers)

    if output:
        from mosaic.exporter import export
        for path in output:
            try:
                export(papers, path)
                rprint(f"[green]Saved:[/green] {path}")
            except ValueError as e:
                rprint(f"[red]{e}[/red]")
                raise typer.Exit(1)

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
    path = dl_paper(paper, cfg["download_dir"], cache, cfg.get("unpaywall", {}).get("email", ""),
                    cfg.get("filename_pattern", "{year}_{source}_{author}_{title}"))
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
    filename_pattern: Annotated[str, typer.Option(help="Set PDF filename pattern (placeholders: {year}, {source}, {author}, {title}, {doi})")] = "",
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
    if filename_pattern:
        cfg["filename_pattern"] = filename_pattern

    if any([elsevier_key, ss_key, unpaywall_email, download_dir, filename_pattern]):
        cfg_mod.save(cfg)
        rprint(f"[green]Config saved to[/green] ~/.config/mosaic/config.toml")

    if show or not any([elsevier_key, ss_key, unpaywall_email, download_dir, filename_pattern]):
        import tomli_w
        console.print_json(data=cfg)


def _print_results(papers: list) -> None:
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", min_width=30, ratio=3)
    table.add_column("Authors", ratio=2)
    table.add_column("Year", width=6)
    table.add_column("DOI", min_width=20, overflow="fold")
    table.add_column("Source", width=16)
    table.add_column("OA", width=4)
    table.add_column("PDF", width=5)

    for i, p in enumerate(papers, 1):
        oa = "[green]yes[/green]" if p.is_open_access else "[red]no[/red]"
        pdf = "[green]✓[/green]" if p.pdf_url else "[dim]–[/dim]"
        doi = p.doi or "[dim]–[/dim]"
        table.add_row(str(i), p.title[:80], p.short_authors, str(p.year or ""), doi, p.source, oa, pdf)

    console.print(table)
    console.print(f"[dim]{len(papers)} result(s)[/dim]")


def _download_all(papers: list, cfg: dict, cache: Cache) -> None:
    email = cfg.get("unpaywall", {}).get("email", "")
    download_dir = cfg["download_dir"]
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")
    ok = fail = skip = 0

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=False) as prog:
        for p in papers:
            if not (p.pdf_url or p.doi):
                skip += 1
                continue
            task = prog.add_task(f"Downloading: {p.title[:50]}…")
            path = dl_paper(p, download_dir, cache, email, pattern)
            prog.remove_task(task)
            if path:
                ok += 1
                rprint(f"  [green]✓[/green] {Path(path).name}")
            else:
                fail += 1
                rprint(f"  [red]✗[/red] {p.title[:60]}")

    console.print(f"\n[bold]Done:[/bold] {ok} downloaded, {fail} failed, {skip} skipped (no PDF)")


@notebook_app.command("create")
def notebook_create(
    name: Annotated[str, typer.Argument(help="Notebook name")],
    query: Annotated[str, typer.Option("--query", "-q", help="Search query to populate the notebook")] = "",
    from_dir: Annotated[Optional[Path], typer.Option("--from-dir", help="Import all PDFs from this directory")] = None,
    max_results: Annotated[int, typer.Option("--max", "-n", help="Max results per source")] = 10,
    oa_only: Annotated[bool, typer.Option("--oa-only", help="Only include open-access papers")] = False,
    pdf_only: Annotated[bool, typer.Option("--pdf-only", help="Only include papers with a downloadable PDF")] = False,
    podcast: Annotated[bool, typer.Option("--podcast", help="Queue an Audio Overview after import")] = False,
    video: Annotated[bool, typer.Option("--video", help="Queue a Video Overview after import")] = False,
    briefing: Annotated[bool, typer.Option("--briefing", help="Queue a Briefing Doc after import")] = False,
    study_guide: Annotated[bool, typer.Option("--study-guide", help="Queue a Study Guide after import")] = False,
    quiz: Annotated[bool, typer.Option("--quiz", help="Queue a Quiz after import")] = False,
    flashcards: Annotated[bool, typer.Option("--flashcards", help="Queue Flashcards after import")] = False,
    infographic: Annotated[bool, typer.Option("--infographic", help="Queue an Infographic after import")] = False,
    slide_deck: Annotated[bool, typer.Option("--slide-deck", help="Queue a Slide Deck after import")] = False,
    data_table: Annotated[bool, typer.Option("--data-table", help="Queue a Data Table after import")] = False,
    mind_map: Annotated[bool, typer.Option("--mind-map", help="Queue a Mind Map after import")] = False,
    year: Annotated[str, typer.Option("--year", "-y", help='Year filter: "2020", "2020-2024", or "2020,2022,2024"')] = "",
    author: Annotated[list[str], typer.Option("--author", "-a", help="Author name filter (repeatable)")] = [],
    journal: Annotated[str, typer.Option("--journal", "-j", help="Journal name filter (substring match)")] = "",
    field: Annotated[str, typer.Option("--field", "-f", help='Scope query to "title", "abstract", or "all" (default)')] = "all",
    raw_query: Annotated[str, typer.Option("--raw-query", help="Raw query sent directly to source APIs, bypassing all field transforms")] = "",
    download_dir: Annotated[str, typer.Option("--download-dir", help="Override PDF download directory for this run")] = "",
):
    """Create a NotebookLM notebook from a search query or a directory of PDFs.

    Requires: pip install 'mosaic-search[notebooklm]' && notebooklm login
    """
    from mosaic.notebooklm_bridge import _require_notebooklm, create_notebook, create_notebook_from_dir
    _require_notebooklm()

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
    _artifacts: set[str] = set()
    if podcast:     _artifacts.add("podcast")
    if video:       _artifacts.add("video")
    if briefing:    _artifacts.add("briefing")
    if study_guide: _artifacts.add("study_guide")
    if quiz:        _artifacts.add("quiz")
    if flashcards:  _artifacts.add("flashcards")
    if infographic: _artifacts.add("infographic")
    if slide_deck:  _artifacts.add("slide_deck")
    if data_table:  _artifacts.add("data_table")
    if mind_map:    _artifacts.add("mind_map")

    # ── from-dir path ─────────────────────────────────────────────────────────
    if from_dir:
        from_dir = Path(from_dir)
        if not from_dir.is_dir():
            rprint(f"[red]Directory not found: {from_dir}[/red]")
            raise typer.Exit(1)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as prog:
            prog.add_task(f"Creating notebook [bold]{name}[/bold] from {from_dir}…")
            try:
                nb_id = asyncio.run(create_notebook_from_dir(name, from_dir, artifacts=_artifacts))
            except ValueError as e:
                rprint(f"[red]{e}[/red]")
                raise typer.Exit(1)
        rprint(f"[green]Notebook created:[/green] https://notebooklm.google.com/notebook/{nb_id}")
        if _artifacts:
            rprint(f"[dim]{', '.join(sorted(_artifacts))} queued — check NotebookLM in a few minutes.[/dim]")
        return

    # ── query path: search → download → import ────────────────────────────────
    sources = _build_sources(cfg)
    cache = Cache(cfg["db_path"])
    email = cfg.get("unpaywall", {}).get("email", "")

    if field not in ("all", "title", "abstract"):
        rprint('[red]--field must be "title", "abstract", or "all"[/red]')
        raise typer.Exit(1)

    filters: SearchFilters | None = None
    if year or author or journal or field != "all" or raw_query:
        filters = SearchFilters(authors=list(author), journal=journal, field=field, raw_query=raw_query)
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
    if pdf_only:
        papers = [p for p in papers if p.pdf_url]

    if not papers:
        rprint("[yellow]No results found.[/yellow]")
        raise typer.Exit()

    rprint(f"[dim]Found {len(papers)} paper(s). Downloading PDFs…[/dim]")

    papers_with_paths: list[tuple] = []
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as prog:
        for p in papers:
            task = prog.add_task(f"{p.title[:55]}…")
            path = dl_paper(p, cfg["download_dir"], cache, email,
                            cfg.get("filename_pattern", "{year}_{source}_{author}_{title}"))
            prog.remove_task(task)
            papers_with_paths.append((p, Path(path) if path else None))

    downloaded = sum(1 for _, path in papers_with_paths if path)
    rprint(f"[dim]{downloaded} PDF(s) downloaded, {len(papers) - downloaded} fallback to URL.[/dim]")

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as prog:
        prog.add_task(f"Importing into NotebookLM notebook [bold]{name}[/bold]…")
        nb_id = asyncio.run(create_notebook(name, papers_with_paths, artifacts=_artifacts))

    rprint(f"[green]Notebook created:[/green] https://notebooklm.google.com/notebook/{nb_id}")
    if _artifacts:
        rprint(f"[dim]{', '.join(sorted(_artifacts))} queued — check NotebookLM in a few minutes.[/dim]")


@auth_app.command("login")
def auth_login(
    name: Annotated[str, typer.Argument(help="Session name, e.g. elsevier, springer, myuni")],
    url: Annotated[str, typer.Option("--url", "-u", help="URL to open in the browser for login")],
) -> None:
    """Open a browser, log in to a site, and save the session for future PDF downloads."""
    import asyncio
    from mosaic.auth import login as do_login
    asyncio.run(do_login(name, url))


@auth_app.command("logout")
def auth_logout(
    name: Annotated[str, typer.Argument(help="Session name to remove")],
) -> None:
    """Remove a saved browser session."""
    from mosaic.auth import delete_session
    if delete_session(name):
        rprint(f"[green]Session removed:[/green] {name}")
    else:
        rprint(f"[yellow]No session found for:[/yellow] {name}")


@auth_app.command("status")
def auth_status() -> None:
    """List all saved browser sessions."""
    from mosaic.auth import list_sessions
    sessions = list_sessions()
    if not sessions:
        rprint("[dim]No saved sessions. Use [bold]mosaic auth login <name> --url <url>[/bold] to add one.[/dim]")
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Domain")
    table.add_column("Saved")
    table.add_column("Valid")
    table.add_column("Path", style="dim")
    for s in sessions:
        valid_cell = "[green]✓[/green]" if s["valid"] else "[red]✗ expired[/red]"
        table.add_row(s["name"], s["domain"], s["saved"], valid_cell, s["path"])
    console.print(table)


if __name__ == "__main__":
    app()
