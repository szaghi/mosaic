"""MOSAIC CLI — Multi-source Scientific Article Indexer and Collector."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import mosaic.config as cfg_mod
from mosaic.config import apply_api_keys
from mosaic.db import Cache
from mosaic.downloader import download as dl_paper
from mosaic.search import search_all
from mosaic.services import build_filters, filter_papers
from mosaic.source_registry import SRC_MAP, build_sources


def _version_callback(value: bool) -> None:
    if value:
        from mosaic import __version__

        rprint(f"mosaic {__version__}")
        raise typer.Exit()


app = typer.Typer(help="MOSAIC — Multi-source Scientific Article Indexer and Collector")
notebook_app = typer.Typer(
    help="Create and populate Google NotebookLM notebooks from search results."
)
auth_app = typer.Typer(help="Manage browser sessions for authenticated PDF access.")
app.add_typer(notebook_app, name="notebook")
app.add_typer(auth_app, name="auth")


@app.callback()
def main(
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
) -> None:
    pass


console = Console()


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    max_results: Annotated[int, typer.Option("--max", "-n", help="Max results per source")] = 10,
    download: Annotated[
        bool, typer.Option("--download", "-d", help="Download available PDFs")
    ] = False,
    oa_only: Annotated[
        bool, typer.Option("--oa-only", help="Show only open access papers")
    ] = False,
    pdf_only: Annotated[
        bool, typer.Option("--pdf-only", help="Show only papers with a downloadable PDF")
    ] = False,
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Limit to one source (arxiv, ss, sd, sp, springer, doaj, epmc, oa, base, core, ads, ieee, zenodo, crossref, dblp, hal, pubmed, pmc, rxiv, pedro, scopus)",
            autocompletion=lambda: list(SRC_MAP.keys()),
        ),
    ] = "",
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
            "--field", "-f", help='Scope query to "title", "abstract", or "all" (default)'
        ),
    ] = "all",
    raw_query: Annotated[
        str,
        typer.Option(
            "--raw-query",
            help="Raw query sent directly to source APIs, bypassing all field transforms",
        ),
    ] = "",
    output: Annotated[
        list[Path],
        typer.Option(
            "--output",
            "-o",
            help="Save results to file (.md, .markdown, .csv, .json, .bib); repeatable",
        ),
    ] = [],
    download_dir: Annotated[
        str, typer.Option("--download-dir", help="Override PDF download directory for this run")
    ] = "",
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort", help='Sort results: "citations" (most cited first) or "year" (newest first)'
        ),
    ] = "",
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Print per-source counts and deduplication stats")
    ] = False,
    zotero: Annotated[bool, typer.Option("--zotero", help="Export results to Zotero")] = False,
    zotero_collection: Annotated[
        str, typer.Option("--zotero-collection", help="Zotero collection name (created if missing)")
    ] = "",
    zotero_local: Annotated[
        bool,
        typer.Option(
            "--zotero-local", help="Force Zotero local API even when an API key is configured"
        ),
    ] = False,
    obsidian: Annotated[
        bool, typer.Option("--obsidian", help="Export results as notes to an Obsidian vault")
    ] = False,
    obsidian_folder: Annotated[
        str,
        typer.Option("--obsidian-folder", help="Override Obsidian vault subfolder for this run"),
    ] = "",
    pedro_fetch_details: Annotated[
        bool,
        typer.Option(
            "--pedro-fetch-details",
            help="Fetch each PEDro record page to get authors, year, DOI and abstract (overrides config for this run)",
        ),
    ] = False,
):
    """Search for papers across all configured sources."""
    cfg = cfg_mod.load()
    if download_dir:
        cfg["download_dir"] = download_dir
    if pedro_fetch_details:
        cfg["sources"]["pedro"]["fetch_details"] = True
    cache = Cache(cfg["db_path"])
    sources = build_sources(cfg)

    # filter by source shorthand
    if source:
        key = source.lower()
        if key not in SRC_MAP:
            rprint(f"[red]Unknown source '{source}'. Use: {', '.join(SRC_MAP.keys())}[/red]")
            raise typer.Exit(1)
        name = SRC_MAP[key]
        sources = [s for s in sources if s.name == name]
        if not sources:
            rprint(
                f"[yellow]Source '{source}' is not active (missing API key or disabled in config).[/yellow]"
            )
            raise typer.Exit(1)

    if field not in ("all", "title", "abstract"):
        rprint('[red]--field must be "title", "abstract", or "all"[/red]')
        raise typer.Exit(1)

    filters, year_warning = build_filters(
        year=year, author=list(author), journal=journal, field=field, raw_query=raw_query
    )
    if year_warning:
        rprint(f"[red]{year_warning}[/red]")
        raise typer.Exit(1)

    errors: list[str] = []
    search_stats: dict = {}
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        prog.add_task(f"Searching {len(sources)} source(s) for [bold]{query}[/bold]…")
        papers = search_all(
            sources,
            query,
            max_per_source=max_results,
            filters=filters,
            errors=errors,
            stats=search_stats,
        )

    for err in errors:
        rprint(f"[yellow]Warning:[/yellow] {err}")

    if verbose:
        _print_search_stats(search_stats, filters)

    _post_process(
        papers,
        cfg,
        cache,
        output=list(output),
        do_download=download,
        sort_by=sort_by,
        oa_only=oa_only,
        pdf_only=pdf_only,
        zotero=zotero,
        zotero_collection=zotero_collection,
        zotero_local=zotero_local,
        obsidian=obsidian,
        obsidian_folder=obsidian_folder,
    )


@app.command()
def similar(
    identifier: Annotated[
        str,
        typer.Argument(
            help="DOI or arXiv ID of the seed paper (e.g. 10.48550/arXiv.1706.03762 or arxiv:1706.03762)"
        ),
    ],
    max_results: Annotated[
        int, typer.Option("--max", "-n", help="Max similar papers to return")
    ] = 10,
    download: Annotated[
        bool, typer.Option("--download", "-d", help="Download available PDFs")
    ] = False,
    oa_only: Annotated[
        bool, typer.Option("--oa-only", help="Show only open-access papers")
    ] = False,
    pdf_only: Annotated[
        bool, typer.Option("--pdf-only", help="Show only papers with a downloadable PDF")
    ] = False,
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort", help='Sort results: "citations" (most cited first) or "year" (newest first)'
        ),
    ] = "",
    output: Annotated[
        list[Path],
        typer.Option(
            "--output",
            "-o",
            help="Save results to file (.md, .markdown, .csv, .json, .bib); repeatable",
        ),
    ] = [],
    download_dir: Annotated[
        str, typer.Option("--download-dir", help="Override PDF download directory for this run")
    ] = "",
    zotero: Annotated[bool, typer.Option("--zotero", help="Export results to Zotero")] = False,
    zotero_collection: Annotated[
        str, typer.Option("--zotero-collection", help="Zotero collection name (created if missing)")
    ] = "",
    zotero_local: Annotated[
        bool,
        typer.Option(
            "--zotero-local", help="Force Zotero local API even when an API key is configured"
        ),
    ] = False,
    obsidian: Annotated[
        bool, typer.Option("--obsidian", help="Export results as notes to an Obsidian vault")
    ] = False,
    obsidian_folder: Annotated[
        str,
        typer.Option("--obsidian-folder", help="Override Obsidian vault subfolder for this run"),
    ] = "",
):
    """Find papers similar to a given paper by DOI or arXiv ID."""
    from mosaic.similar import find_similar

    cfg = cfg_mod.load()
    if download_dir:
        cfg["download_dir"] = download_dir
    cache = Cache(cfg["db_path"])

    oa_email = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key = cfg.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        prog.add_task(f"Finding papers similar to [bold]{identifier}[/bold]…")
        try:
            seed_title, papers = find_similar(
                identifier,
                max_results=max_results,
                oa_email=oa_email,
                ss_api_key=ss_api_key,
            )
        except Exception as e:
            rprint(f"[red]Error looking up paper: {e}[/red]")
            raise typer.Exit(1) from None

    if seed_title is None:
        rprint(f"[red]Paper not found:[/red] {identifier}")
        rprint("[dim]Check that the DOI or arXiv ID is correct.[/dim]")
        raise typer.Exit(1)

    rprint(f"[bold]Similar to:[/bold] {seed_title}\n")

    _post_process(
        papers,
        cfg,
        cache,
        output=list(output),
        do_download=download,
        sort_by=sort_by,
        oa_only=oa_only,
        pdf_only=pdf_only,
        zotero=zotero,
        zotero_collection=zotero_collection,
        zotero_local=zotero_local,
        obsidian=obsidian,
        obsidian_folder=obsidian_folder,
    )


@app.command()
def get(
    doi: Annotated[str | None, typer.Argument(help="DOI of the paper to download")] = None,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from", help="BibTeX (.bib) or CSV (.csv) file containing DOIs to bulk-download"
        ),
    ] = None,
    oa_only: Annotated[
        bool,
        typer.Option("--oa-only", help="Treat unresolvable papers as skipped rather than failed"),
    ] = False,
    download_dir: Annotated[
        str, typer.Option("--download-dir", help="Override PDF download directory for this run")
    ] = "",
    zotero: Annotated[
        bool, typer.Option("--zotero", help="Export downloaded paper(s) to Zotero")
    ] = False,
    zotero_collection: Annotated[
        str, typer.Option("--zotero-collection", help="Zotero collection name (created if missing)")
    ] = "",
    zotero_local: Annotated[
        bool,
        typer.Option(
            "--zotero-local", help="Force Zotero local API even when an API key is configured"
        ),
    ] = False,
    obsidian: Annotated[
        bool, typer.Option("--obsidian", help="Export paper(s) as notes to an Obsidian vault")
    ] = False,
    obsidian_folder: Annotated[
        str,
        typer.Option("--obsidian-folder", help="Override Obsidian vault subfolder for this run"),
    ] = "",
):
    """Download a paper by DOI, or bulk-download all DOIs from a .bib/.csv file."""
    cfg = cfg_mod.load()
    if download_dir:
        cfg["download_dir"] = download_dir
    cache = Cache(cfg["db_path"])

    if from_file and doi:
        rprint("[red]Provide either a DOI argument or --from, not both.[/red]")
        raise typer.Exit(1)

    if from_file:
        _bulk_download(
            from_file,
            cfg,
            cache,
            oa_only,
            zotero=zotero,
            zotero_collection=zotero_collection,
            zotero_local=zotero_local,
            obsidian=obsidian,
            obsidian_folder=obsidian_folder,
        )
        return

    if doi is None:
        rprint("[red]Provide a DOI argument or use --from <file> for bulk download.[/red]")
        raise typer.Exit(1)

    from mosaic.models import Paper

    paper = Paper(title=doi, doi=doi, source="manual")
    path = dl_paper(
        paper,
        cfg["download_dir"],
        cache,
        cfg.get("unpaywall", {}).get("email", ""),
        cfg.get("filename_pattern", "{year}_{source}_{author}_{title}"),
    )
    if path:
        rprint(f"[green]Saved:[/green] {path}")
    else:
        rprint("[red]Could not find a downloadable PDF for this DOI.[/red]")

    if zotero:
        pdf_map = {paper.uid: path} if path else {}
        _push_to_zotero(
            [paper],
            cfg,
            collection_name=zotero_collection,
            force_local=zotero_local,
            pdf_map=pdf_map,
        )

    if obsidian:
        _push_to_obsidian([paper], cfg, subfolder_override=obsidian_folder)


@app.command()
def config(
    show: Annotated[bool, typer.Option("--show", help="Print current config")] = False,
    elsevier_key: Annotated[str, typer.Option(help="Set Elsevier API key")] = "",
    ss_key: Annotated[str, typer.Option(help="Set Semantic Scholar API key")] = "",
    ncbi_key: Annotated[str, typer.Option(help="Set NCBI/PubMed API key")] = "",
    zotero_key: Annotated[str, typer.Option(help="Set Zotero API key (web API)")] = "",
    unpaywall_email: Annotated[str, typer.Option(help="Set Unpaywall email")] = "",
    download_dir: Annotated[str, typer.Option(help="Set download directory")] = "",
    filename_pattern: Annotated[
        str,
        typer.Option(
            help="Set PDF filename pattern (placeholders: {year}, {source}, {author}, {title}, {doi})"
        ),
    ] = "",
    pedro_fair_use: Annotated[
        bool,
        typer.Option(
            "--pedro-fair-use/--no-pedro-fair-use",
            help="Acknowledge PEDro fair-use policy to enable the source",
        ),
    ] = None,
    pedro_fetch_details: Annotated[
        bool,
        typer.Option(
            "--pedro-fetch-details/--no-pedro-fetch-details",
            help="Fetch each PEDro record page to get authors, year, DOI and abstract (slower)",
        ),
    ] = None,
):
    """View or update MOSAIC configuration."""
    cfg = cfg_mod.load()

    api_keys_changed = apply_api_keys(
        cfg, {"elsevier_key": elsevier_key, "ss_key": ss_key, "ncbi_key": ncbi_key}
    )
    # Also set PMC key to same NCBI key
    if ncbi_key:
        cfg["sources"]["pmc"]["api_key"] = ncbi_key
    if zotero_key:
        cfg["zotero"]["api_key"] = zotero_key
        # auto-discover and cache the user ID
        from mosaic.zotero import ZoteroClient

        client = ZoteroClient(api_key=zotero_key)
        try:
            uid = client.discover_user_id()
            cfg["zotero"]["user_id"] = uid
            rprint(f"[green]Zotero web API configured for user {uid}[/green]")
        except Exception as e:
            rprint(f"[yellow]Could not auto-discover Zotero user ID: {e}[/yellow]")
    if unpaywall_email:
        cfg["unpaywall"]["email"] = unpaywall_email
    if download_dir:
        cfg["download_dir"] = download_dir
    if filename_pattern:
        cfg["filename_pattern"] = filename_pattern
    if pedro_fair_use is not None:
        cfg["sources"]["pedro"]["acknowledge_fair_use"] = pedro_fair_use
        if pedro_fair_use:
            rprint("[green]PEDro fair-use policy acknowledged. Source is now enabled.[/green]")
        else:
            rprint(
                "[yellow]PEDro fair-use acknowledgement removed. Source is now disabled.[/yellow]"
            )
    if pedro_fetch_details is not None:
        cfg["sources"]["pedro"]["fetch_details"] = pedro_fetch_details
        if pedro_fetch_details:
            rprint("[green]PEDro detail fetching enabled (authors, year, DOI, abstract).[/green]")
        else:
            rprint("[yellow]PEDro detail fetching disabled.[/yellow]")

    _pedro_changed = pedro_fair_use is not None or pedro_fetch_details is not None
    _any_changed = any(
        [
            api_keys_changed,
            zotero_key,
            unpaywall_email,
            download_dir,
            filename_pattern,
            _pedro_changed,
        ]
    )
    if _any_changed:
        cfg_mod.save(cfg)
        rprint("[green]Config saved to[/green] ~/.config/mosaic/config.toml")

    if show or not _any_changed:
        console.print_json(data=cfg)


def _bulk_download(
    from_file: Path,
    cfg: dict,
    cache: Cache,
    oa_only: bool,
    zotero: bool = False,
    zotero_collection: str = "",
    zotero_local: bool = False,
    obsidian: bool = False,
    obsidian_folder: str = "",
) -> None:
    from mosaic.bulk import read_dois
    from mosaic.models import Paper

    if not from_file.exists():
        rprint(f"[red]File not found: {from_file}[/red]")
        raise typer.Exit(1)

    try:
        dois = read_dois(from_file)
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    if not dois:
        rprint(f"[yellow]No DOIs found in {from_file.name}[/yellow]")
        raise typer.Exit()

    rprint(f"[dim]Found {len(dois)} DOI(s) in {from_file.name}[/dim]")

    email = cfg.get("unpaywall", {}).get("email", "")
    download_dir = cfg["download_dir"]
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")
    ok = fail = skip = 0
    papers_list: list = []
    pdf_map: dict[str, str] = {}

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=False
    ) as prog:
        for doi in dois:
            paper = Paper(title=doi, doi=doi, source="manual")
            papers_list.append(paper)
            task = prog.add_task(f"{doi}…")
            path = dl_paper(paper, download_dir, cache, email, pattern)
            prog.remove_task(task)
            if path:
                ok += 1
                pdf_map[paper.uid] = path
                rprint(f"  [green]✓[/green] {Path(path).name}")
            elif oa_only:
                skip += 1
                rprint(f"  [dim]–[/dim] {doi} (no OA copy)")
            else:
                fail += 1
                rprint(f"  [red]✗[/red] {doi}")

    parts = [f"[bold]{ok}[/bold] downloaded"]
    if fail:
        parts.append(f"[red]{fail} failed[/red]")
    if skip:
        parts.append(f"[dim]{skip} skipped (no OA copy)[/dim]")
    console.print(f"\n[bold]Done:[/bold] {', '.join(parts)}")

    if zotero and papers_list:
        _push_to_zotero(
            papers_list,
            cfg,
            collection_name=zotero_collection,
            force_local=zotero_local,
            pdf_map=pdf_map,
        )

    if obsidian and papers_list:
        _push_to_obsidian(papers_list, cfg, subfolder_override=obsidian_folder)


def _print_search_stats(stats: dict, filters) -> None:
    from rich.panel import Panel

    per_source = stats.get("per_source", {})
    raw_total = stats.get("raw_total", 0)
    unique = stats.get("unique", 0)
    merged = stats.get("merged", 0)

    source_names = list(per_source.keys())
    sources_line = "  ".join(f"[bold]{n}[/bold]=[cyan]{c}[/cyan]" for n, c in per_source.items())
    if not source_names:
        sources_line = "[dim]none[/dim]"

    filter_parts = []
    if filters:
        if filters.year_from and filters.year_to:
            filter_parts.append(f"year={filters.year_from}–{filters.year_to}")
        elif filters.year_from:
            filter_parts.append(f"year={filters.year_from}")
        elif filters.years:
            filter_parts.append(f"year={','.join(str(y) for y in filters.years)}")
        if filters.authors:
            filter_parts.append(f"author={', '.join(filters.authors)}")
        if filters.journal:
            filter_parts.append(f"journal={filters.journal}")
        if filters.field and filters.field != "all":
            filter_parts.append(f"field={filters.field}")
    filters_line = "  ".join(filter_parts) if filter_parts else "[dim]none[/dim]"

    lines = [
        f"[dim]Sources   [/dim] {', '.join(source_names) or '[dim]none[/dim]'}",
        f"[dim]Raw       [/dim] {sources_line}  [dim]→ {raw_total} total[/dim]",
        f"[dim]Unique    [/dim] [bold]{unique}[/bold] papers[dim]  ({merged} merged by DOI)[/dim]",
        f"[dim]Filters   [/dim] {filters_line}",
    ]
    console.print(
        Panel(
            "\n".join(lines), title="[bold]Search stats[/bold]", border_style="dim", padding=(0, 1)
        )
    )


def _post_process(
    papers: list,
    cfg: dict,
    cache: Cache,
    *,
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
) -> None:
    """Shared post-processing: filter, export, download, push to Zotero/Obsidian."""
    if sort_by and sort_by not in ("citations", "year"):
        rprint(f'[red]Unknown --sort value "{sort_by}". Use: citations, year[/red]')
        raise typer.Exit(1)
    papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only, sort_by=sort_by)

    if not papers:
        rprint("[yellow]No results found.[/yellow]")
        raise typer.Exit()

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
                raise typer.Exit(1) from None

    pdf_map: dict[str, str] = {}
    if do_download:
        pdf_map = _download_all(papers, cfg, cache)

    if zotero:
        _push_to_zotero(
            papers,
            cfg,
            collection_name=zotero_collection,
            force_local=zotero_local,
            pdf_map=pdf_map,
        )

    if obsidian:
        _push_to_obsidian(papers, cfg, subfolder_override=obsidian_folder)


def _print_results(papers: list) -> None:
    show_citations = any(p.citation_count is not None for p in papers)

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", min_width=30, ratio=3)
    table.add_column("Authors", ratio=2)
    table.add_column("Year", width=6)
    table.add_column("DOI", min_width=20, overflow="fold")
    table.add_column("Source", width=16)
    table.add_column("OA", width=4)
    table.add_column("PDF", width=5)
    if show_citations:
        table.add_column("Cited", width=7, justify="right")

    for i, p in enumerate(papers, 1):
        oa = "[green]yes[/green]" if p.is_open_access else "[red]no[/red]"
        pdf = "[green]✓[/green]" if p.pdf_url else "[dim]–[/dim]"
        doi = p.doi or "[dim]–[/dim]"
        row = [str(i), p.title[:80], p.short_authors, str(p.year or ""), doi, p.source, oa, pdf]
        if show_citations:
            cited = str(p.citation_count) if p.citation_count is not None else "[dim]–[/dim]"
            row.append(cited)
        table.add_row(*row)

    console.print(table)
    console.print(f"[dim]{len(papers)} result(s)[/dim]")


def _download_all(papers: list, cfg: dict, cache: Cache) -> dict[str, str]:
    """Download PDFs for *papers*. Returns a ``{paper.uid: local_path}`` map."""
    email = cfg.get("unpaywall", {}).get("email", "")
    download_dir = cfg["download_dir"]
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")
    ok = fail = skip = 0
    pdf_map: dict[str, str] = {}

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=False
    ) as prog:
        for p in papers:
            if not (p.pdf_url or p.doi):
                skip += 1
                continue
            task = prog.add_task(f"Downloading: {p.title[:50]}…")
            path = dl_paper(p, download_dir, cache, email, pattern)
            prog.remove_task(task)
            if path:
                ok += 1
                pdf_map[p.uid] = path
                rprint(f"  [green]✓[/green] {Path(path).name}")
            else:
                fail += 1
                rprint(f"  [red]✗[/red] {p.title[:60]}")

    console.print(f"\n[bold]Done:[/bold] {ok} downloaded, {fail} failed, {skip} skipped (no PDF)")
    return pdf_map


def _push_to_zotero(
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


def _push_to_obsidian(
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
            "--field", "-f", help='Scope query to "title", "abstract", or "all" (default)'
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
        _require_notebooklm,
        create_notebook,
        create_notebook_from_dir,
    )

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
    _artifact_flags = {
        "podcast": podcast, "video": video, "briefing": briefing,
        "study_guide": study_guide, "quiz": quiz, "flashcards": flashcards,
        "infographic": infographic, "slide_deck": slide_deck,
        "data_table": data_table, "mind_map": mind_map,
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
                nb_id = asyncio.run(create_notebook_from_dir(name, from_dir, artifacts=_artifacts))
            except ValueError as e:
                rprint(f"[red]{e}[/red]")
                raise typer.Exit(1) from None
        rprint(f"[green]Notebook created:[/green] https://notebooklm.google.com/notebook/{nb_id}")
        if _artifacts:
            rprint(
                f"[dim]{', '.join(sorted(_artifacts))} queued — check NotebookLM in a few minutes.[/dim]"
            )
        return

    # ── query path: search → download → import ────────────────────────────────
    sources = build_sources(cfg)
    cache = Cache(cfg["db_path"])
    email = cfg.get("unpaywall", {}).get("email", "")

    if field not in ("all", "title", "abstract"):
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
        rprint(f"[yellow]Warning:[/yellow] {err}")

    papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only)

    if not papers:
        rprint("[yellow]No results found.[/yellow]")
        raise typer.Exit()

    rprint(f"[dim]Found {len(papers)} paper(s). Downloading PDFs…[/dim]")

    papers_with_paths: list[tuple] = []
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        for p in papers:
            task = prog.add_task(f"{p.title[:55]}…")
            path = dl_paper(
                p,
                cfg["download_dir"],
                cache,
                email,
                cfg.get("filename_pattern", "{year}_{source}_{author}_{title}"),
            )
            prog.remove_task(task)
            papers_with_paths.append((p, Path(path) if path else None))

    downloaded = sum(1 for _, path in papers_with_paths if path)
    rprint(
        f"[dim]{downloaded} PDF(s) downloaded, {len(papers) - downloaded} fallback to URL.[/dim]"
    )

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
    ) as prog:
        prog.add_task(f"Importing into NotebookLM notebook [bold]{name}[/bold]…")
        nb_id = asyncio.run(create_notebook(name, papers_with_paths, artifacts=_artifacts))

    rprint(f"[green]Notebook created:[/green] https://notebooklm.google.com/notebook/{nb_id}")
    if _artifacts:
        rprint(
            f"[dim]{', '.join(sorted(_artifacts))} queued — check NotebookLM in a few minutes.[/dim]"
        )


@app.command()
def ui(
    host: Annotated[str, typer.Option(help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port number")] = 5555,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Don't auto-open browser")
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable Flask debug mode")] = False,
):
    """Launch the MOSAIC web interface."""
    try:
        from mosaic.ui import create_app
    except ImportError:
        rprint("[red]Flask is required for the web UI. Install it with:[/red]")
        rprint("  pip install 'mosaic-search[ui]'")
        raise typer.Exit(1) from None

    flask_app = create_app()
    if not no_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=[f"http://{host}:{port}"]).start()

    if debug:
        flask_app.run(host=host, port=port, debug=True)
    else:
        from waitress import create_server

        server = create_server(flask_app, host=host, port=port)
        rprint(
            f"[green]MOSAIC[/green] running at [link]http://{host}:{port}[/link]  (Ctrl+C to stop)"
        )
        server.run()


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
        rprint(
            "[dim]No saved sessions. Use [bold]mosaic auth login <name> --url <url>[/bold] to add one.[/dim]"
        )
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
