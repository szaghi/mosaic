"""MOSAIC CLI — Multi-source Scientific Article Indexer and Collector."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, List, Optional

import typer
from rich import box, print as rprint
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import mosaic.config as cfg_mod
from mosaic.config import apply_api_keys
from mosaic.db import Cache
from mosaic.downloader import download as dl_paper
from mosaic.search import search_all
from mosaic.services import build_filters, filter_papers, sort_by_relevance
from mosaic.errors import set_verbose_logging
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
cache_app = typer.Typer(help="Inspect and manage the local SQLite cache.")
skill_app = typer.Typer(help="Manage the bundled MOSAIC Claude Code skill.")
app.add_typer(notebook_app, name="notebook")
app.add_typer(auth_app, name="auth")
app.add_typer(cache_app, name="cache")
app.add_typer(skill_app, name="skill")


_verbose: bool = False


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
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Show warnings and per-source stats"),
    ] = False,
) -> None:
    global _verbose
    _verbose = verbose
    set_verbose_logging(verbose)


console = Console()


def warn(msg: str) -> None:
    """Print a warning — only when --verbose is active."""
    if _verbose:
        rprint(msg)


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
            "--field", "-f",
            help='Scope query to "title", "abstract", or "all" (default)',
            autocompletion=lambda: _FIELD_VALUES,
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
            help="Save results to file (.md, .markdown, .csv, .json, .bib, .ris); repeatable",
        ),
    ] = [],
    download_dir: Annotated[
        str, typer.Option("--download-dir", help="Override PDF download directory for this run")
    ] = "",
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort",
            help='Sort results: "citations" (most cited first), "year" (newest first), or "relevance" (most relevant first)',
            autocompletion=lambda: _SORT_VALUES,
        ),
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
    pedro_fetch_details: Annotated[
        bool,
        typer.Option(
            "--pedro-fetch-details",
            help="Fetch each PEDro record page to get authors, year, DOI and abstract (overrides config for this run)",
        ),
    ] = False,
    stats: Annotated[
        bool, typer.Option("--stats", help="Print per-source counts and deduplication stats")
    ] = False,
    cached: Annotated[
        bool, typer.Option("--cached", help="Search only the local cache — no network requests")
    ] = False,
    prefer_cache: Annotated[
        bool,
        typer.Option(
            "--prefer-cache",
            help="Prefer rich cached records over freshly fetched data for known papers",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emit structured JSON to stdout instead of a table (useful for scripting and AI agents)",
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

    if cached:
        filters, year_warning = build_filters(
            year=year, author=list(author), journal=journal, field=field, raw_query=raw_query
        )
        if year_warning:
            rprint(f"[red]{year_warning}[/red]")
            raise typer.Exit(1)
        if not json_output:
            rprint(f"[dim]Searching local cache for '{query}'…[/dim]")
        papers = cache.search_local(query)
        if filters:
            papers = [p for p in papers if filters.match(p)]
        if json_output:
            _emit_json(papers, query=query)
            return
        _post_process(
            papers,
            cfg,
            cache,
            query=query,
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
        return

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
                f"[dark_orange]Source '{source}' is not active (missing API key or disabled in config).[/dark_orange]"
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
    if json_output:
        papers = search_all(
            sources,
            query,
            max_per_source=max_results,
            filters=filters,
            errors=errors,
            stats=search_stats,
        )
    else:
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

    if not json_output:
        for err in errors:
            warn(f"[dark_orange]Warning:[/dark_orange] {err}")

    if prefer_cache:
        rich = cache.rich_uids()
        papers = [cache.get_by_uid(p.uid) or p if p.uid in rich else p for p in papers]

    if json_output:
        papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only, sort_by=sort_by if sort_by != "relevance" else "")
        if sort_by == "relevance":
            papers = sort_by_relevance(query, papers, cfg)
        for p in papers:
            cache.save(p)
        if output:
            from mosaic.exporter import export
            for path in list(output):
                export(papers, path)
        _emit_json(papers, query=query, errors=errors)
        return

    if stats:
        _print_search_stats(search_stats, filters)

    _post_process(
        papers,
        cfg,
        cache,
        query=query,
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
            "--sort",
            help='Sort results: "citations" (most cited first), "year" (newest first), or "relevance" (most relevant first)',
            autocompletion=lambda: _SORT_VALUES,
        ),
    ] = "",
    output: Annotated[
        list[Path],
        typer.Option(
            "--output",
            "-o",
            help="Save results to file (.md, .markdown, .csv, .json, .bib, .ris); repeatable",
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
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emit structured JSON to stdout instead of a table (useful for scripting and AI agents)",
        ),
    ] = False,
):
    """Find papers similar to a given paper by DOI or arXiv ID."""
    from mosaic.similar import find_similar

    cfg = cfg_mod.load()
    if download_dir:
        cfg["download_dir"] = download_dir
    cache = Cache(cfg["db_path"])

    oa_email = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key = cfg.get("sources", {}).get("semantic_scholar", {}).get("api_key", "")

    if json_output:
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
    else:
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
        if json_output:
            import json as _json
            print(_json.dumps({"status": "error", "query": identifier, "errors": ["Paper not found"]}, indent=2))
            raise typer.Exit(1)
        rprint(f"[red]Paper not found:[/red] {identifier}")
        rprint("[dim]Check that the DOI or arXiv ID is correct.[/dim]")
        raise typer.Exit(1)

    if json_output:
        papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only, sort_by=sort_by if sort_by != "relevance" else "")
        if sort_by == "relevance":
            papers = sort_by_relevance(seed_title or identifier, papers, cfg)
        for p in papers:
            cache.save(p)
        if output:
            from mosaic.exporter import export
            for path in list(output):
                export(papers, path)
        _emit_json(papers, query=identifier, seed=seed_title)
        return

    rprint(f"[bold]Similar to:[/bold] {seed_title}\n")

    _post_process(
        papers,
        cfg,
        cache,
        query=seed_title or identifier,
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

    _bare = Paper(title=doi, doi=doi, source="manual")
    paper = cache.get_by_uid(_bare.uid) or _bare
    if paper is not _bare:
        rprint(f"[dim]Found in local cache: {paper.title[:80]}[/dim]")
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
def index(
    reindex: Annotated[bool, typer.Option("--reindex", help="Re-embed all papers, even already-indexed ones")] = False,
    query: Annotated[str, typer.Option("--query", "-q", help="Embed only papers matching this query")] = "",
    from_file: Annotated[Optional[Path], typer.Option("--from", help="Embed only papers from a .bib or .csv file")] = None,
    batch_size: Annotated[int, typer.Option("--batch-size", help="Texts per embedding API call")] = 96,
):
    """Build or update the vector index for semantic search and RAG."""
    from mosaic.rag import index_papers

    cfg = cfg_mod.load()
    cache = Cache(cfg["db_path"])

    # Gather candidate papers
    if from_file:
        from mosaic.bulk import read_dois
        dois = read_dois(from_file)
        papers_from_file = []
        for doi in dois:
            papers_from_file.extend(cache.search_local(doi))
        seen: set[str] = set()
        unique: list = []
        for p in papers_from_file:
            if p.uid not in seen:
                seen.add(p.uid)
                unique.append(p)
        papers = unique
    elif query:
        papers = cache.search_local(query)
    else:
        papers = cache.get_all_papers()

    if not papers:
        rprint("[yellow]No papers found in cache. Run some searches first.[/yellow]")
        raise typer.Exit()

    rprint(f"[cyan]Indexing {len(papers)} papers…[/cyan]")
    try:
        newly, skipped = index_papers(papers, cfg, cache, reindex=reindex)
        rprint(f"[green]Indexed {newly} new paper(s).[/green] {skipped} already indexed.")
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question or topic to analyse")],
    mode: Annotated[str, typer.Option("--mode", help="synthesis (default), gaps, compare, extract")] = "synthesis",
    query: Annotated[str, typer.Option("--query", "-q", help="Pre-filter: restrict to papers matching this FTS query")] = "",
    from_file: Annotated[Optional[Path], typer.Option("--from", help="Pre-filter: restrict to papers from a .bib or .csv file")] = None,
    year: Annotated[Optional[str], typer.Option("--year", "-y", help="Year or range filter (e.g. 2020-2024)")] = None,
    n: Annotated[Optional[int], typer.Option("-n", "--top", help="Override rag.top_k for this query")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Write answer to file (.md or .json)")] = None,
    show_sources: Annotated[bool, typer.Option("--show-sources", help="Print retrieved papers before the answer")] = False,
):
    """Ask a question about your cached papers using RAG."""
    from mosaic.rag import ask as rag_ask
    from rich.markdown import Markdown
    from rich.rule import Rule

    cfg = cfg_mod.load()
    cache = Cache(cfg["db_path"])

    # Build pre_filter from --query or --from
    pre_filter: Optional[list[str]] = None
    if from_file:
        from mosaic.bulk import read_dois
        dois = read_dois(from_file)
        papers_from_file = []
        for doi in dois:
            papers_from_file.extend(cache.search_local(doi))
        pre_filter = list({p.uid for p in papers_from_file})
    elif query:
        filtered = cache.search_local(query)
        pre_filter = [p.uid for p in filtered]

    # Apply year filter to pre_filter if provided
    if year and pre_filter is not None:
        from mosaic.services import build_filters, filter_papers
        filters, _ = build_filters(year=year)
        all_papers = cache.get_papers_by_uids(pre_filter)
        filtered_papers = filter_papers(all_papers, oa_only=False, pdf_only=False)
        filtered_papers = [p for p in all_papers if filters and filters.match(p)]
        pre_filter = [p.uid for p in filtered_papers]
    elif year:
        from mosaic.services import build_filters
        filters, _ = build_filters(year=year)
        all_papers = cache.get_all_papers()
        filtered_papers = [p for p in all_papers if filters and filters.match(p)]
        pre_filter = [p.uid for p in filtered_papers]

    valid_modes = {"synthesis", "gaps", "compare", "extract"}
    if mode not in valid_modes:
        rprint(f"[red]Unknown mode {mode!r}. Choose from: {', '.join(sorted(valid_modes))}[/red]")
        raise typer.Exit(1)

    console.print(Rule(f"[cyan]mosaic ask[/cyan] · mode: {mode}"))

    try:
        answer, papers = rag_ask(question, cfg, cache, mode=mode, k=n, pre_filter=pre_filter)
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if show_sources:
        rprint(f"\n[bold]Sources retrieved ({len(papers)}):[/bold]")
        for i, p in enumerate(papers, 1):
            authors = ", ".join(p.authors[:2]) if p.authors else "Unknown"
            rprint(f"  [{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})")
        rprint()

    console.print(Markdown(answer))

    # References footer
    rprint("\n[bold]References[/bold]")
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:3]) if p.authors else "Unknown"
        if len(p.authors) > 3:
            authors += " et al."
        rprint(f"  [{i}] {p.title or 'Untitled'} — {authors}, {p.year or '?'}")

    if output:
        if str(output).endswith(".json"):
            import json as _json
            data = {
                "question": question,
                "mode": mode,
                "answer": answer,
                "sources": [
                    {"title": p.title, "authors": p.authors, "year": p.year, "doi": p.doi}
                    for p in papers
                ],
            }
            output.write_text(_json.dumps(data, indent=2, default=str))
        else:
            # Markdown
            lines = [f"# {question}\n", f"*Mode: {mode}*\n\n", answer, "\n\n## References\n"]
            for i, p in enumerate(papers, 1):
                authors = ", ".join(p.authors[:3]) if p.authors else "Unknown"
                lines.append(f"- [{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})")
            output.write_text("\n".join(lines))
        rprint(f"[green]Answer saved to {output}[/green]")


@app.command()
def chat(
    query: Annotated[str, typer.Option("--query", "-q", help="Narrow retrieval pool to papers matching this query")] = "",
    from_file: Annotated[Optional[Path], typer.Option("--from", help="Narrow retrieval pool to papers from a .bib or .csv file")] = None,
    mode: Annotated[str, typer.Option("--mode", help="Default prompt mode: synthesis, gaps, compare, extract")] = "synthesis",
):
    """Interactive RAG chat session over your cached papers."""
    from mosaic.rag import _PROMPTS, _build_context, retrieve
    from rich.markdown import Markdown
    from rich.rule import Rule

    cfg = cfg_mod.load()
    cache = Cache(cfg["db_path"])

    # Build pre_filter
    pre_filter: Optional[list[str]] = None
    if from_file:
        from mosaic.bulk import read_dois
        dois = read_dois(from_file)
        papers_from_file = []
        for doi in dois:
            papers_from_file.extend(cache.search_local(doi))
        pre_filter = list({p.uid for p in papers_from_file})
    elif query:
        filtered = cache.search_local(query)
        pre_filter = [p.uid for p in filtered]

    current_mode = mode
    history: list[dict] = []

    console.print(Rule("[cyan]mosaic chat[/cyan]"))
    rprint("[dim]Commands: /mode <synthesis|gaps|compare|extract>  /sources  /clear  /quit[/dim]\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            rprint("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            parts = user_input.split(None, 1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if cmd == "/quit":
                rprint("[dim]Goodbye.[/dim]")
                break
            elif cmd == "/clear":
                history.clear()
                rprint("[dim]Conversation history cleared.[/dim]")
            elif cmd == "/mode":
                valid = {"synthesis", "gaps", "compare", "extract"}
                if arg in valid:
                    current_mode = arg
                    rprint(f"[dim]Mode set to {current_mode}.[/dim]")
                else:
                    rprint(f"[red]Unknown mode. Choose from: {', '.join(sorted(valid))}[/red]")
            elif cmd == "/sources":
                show_papers = retrieve(query or "research", cfg, cache, pre_filter=pre_filter)
                for i, p in enumerate(show_papers, 1):
                    authors = ", ".join(p.authors[:2]) if p.authors else "Unknown"
                    rprint(f"  [{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})")
            else:
                rprint(f"[red]Unknown command: {cmd}[/red]")
            continue

        # Retrieve papers for this turn
        try:
            papers = retrieve(user_input, cfg, cache, pre_filter=pre_filter)
        except Exception as e:
            rprint(f"[red]Retrieval error: {e}[/red]")
            continue

        if not papers:
            rprint("[yellow]No indexed papers found. Run `mosaic index` first.[/yellow]")
            continue

        context = _build_context(papers)
        template = _PROMPTS.get(current_mode, _PROMPTS["synthesis"])
        system_prompt = template.format(query=user_input, context=context)

        # Build messages with history
        messages = [{"role": "user", "content": system_prompt}]
        for h in history[-6:]:  # last 3 turns
            messages.append(h)
        # The actual question is already in the system prompt; add a short user turn
        messages.append({"role": "user", "content": user_input})

        try:
            import httpx as _httpx
            llm_cfg = cfg.get("llm", {})
            provider = llm_cfg.get("provider", "").lower()
            api_key = llm_cfg.get("api_key", "")
            llm_model = llm_cfg.get("model", "") or (
                "gpt-4o-mini" if provider == "openai" else "claude-haiku-4-5-20251001"
            )
            base_url = llm_cfg.get("base_url", "").rstrip("/")

            if not api_key or not provider:
                rprint(
                    "[red]No LLM configured. Run: mosaic config --llm-provider ... "
                    "--llm-api-key ... --llm-model ...[/red]"
                )
                continue

            if provider == "openai" or base_url:
                url = (
                    f"{base_url}/chat/completions"
                    if base_url
                    else "https://api.openai.com/v1/chat/completions"
                )
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                resp = _httpx.post(
                    url,
                    headers=headers,
                    json={"model": llm_model, "messages": messages},
                    timeout=180,
                )
                resp.raise_for_status()
                answer = resp.json()["choices"][0]["message"]["content"]
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
                resp = _httpx.post(
                    url,
                    headers=headers,
                    json={"model": llm_model, "max_tokens": 2048, "messages": messages},
                    timeout=180,
                )
                resp.raise_for_status()
                answer = resp.json()["content"][0]["text"]
            else:
                rprint(f"[red]Unknown provider: {provider}[/red]")
                continue

            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": answer})

            rprint("\n[bold cyan]mosaic:[/bold cyan]")
            console.print(Markdown(answer))
            rprint()

        except Exception as e:
            rprint(f"[red]LLM error: {e}[/red]")


@app.command()
def config(  # noqa: PLR0912, PLR0915
    show: Annotated[bool, typer.Option("--show", help="Print current config")] = False,
    # --- API keys ---
    elsevier_key: Annotated[str, typer.Option(help="Set Elsevier / ScienceDirect API key")] = "",
    ss_key: Annotated[str, typer.Option(help="Set Semantic Scholar API key")] = "",
    ncbi_key: Annotated[str, typer.Option(help="Set NCBI API key (used for PubMed and PMC)")] = "",
    core_key: Annotated[str, typer.Option(help="Set CORE API key")] = "",
    ads_key: Annotated[str, typer.Option(help="Set NASA ADS API key")] = "",
    ieee_key: Annotated[str, typer.Option(help="Set IEEE Xplore API key")] = "",
    springer_key: Annotated[str, typer.Option(help="Set Springer API key")] = "",
    scopus_key: Annotated[str, typer.Option(help="Set Scopus API key")] = "",
    scopus_inst_token: Annotated[str, typer.Option(help="Set Scopus institutional token")] = "",
    zenodo_key: Annotated[str, typer.Option(help="Set Zenodo API key")] = "",
    zotero_key: Annotated[str, typer.Option(help="Set Zotero API key (web API)")] = "",
    unpaywall_email: Annotated[str, typer.Option(help="Set Unpaywall email")] = "",
    # --- download / files ---
    download_dir: Annotated[str, typer.Option(help="Set PDF download directory")] = "",
    db_path: Annotated[str, typer.Option(help="Set SQLite cache path")] = "",
    filename_pattern: Annotated[
        str,
        typer.Option(
            help="Set PDF filename pattern (placeholders: {year}, {source}, {author}, {title}, {doi})"
        ),
    ] = "",
    rate_limit_delay: Annotated[
        Optional[float],
        typer.Option(help="Set default delay between API calls in seconds"),
    ] = None,
    # --- source enable/disable ---
    enable_source: Annotated[
        Optional[List[str]],
        typer.Option(
            "--enable-source",
            help="Enable a source by name (repeatable). Known names: arxiv, semantic_scholar, sciencedirect, doaj, europepmc, openalex, base, springer_api, core, nasa_ads, ieee, zenodo, crossref, dblp, hal, pubmed, pmc, biorxiv, pedro, scopus",
        ),
    ] = None,
    disable_source: Annotated[
        Optional[List[str]],
        typer.Option(
            "--disable-source",
            help="Disable a source by name (repeatable). Same names as --enable-source",
        ),
    ] = None,
    # --- obsidian ---
    obsidian_vault: Annotated[str, typer.Option(help="Set Obsidian vault path")] = "",
    obsidian_subfolder: Annotated[str, typer.Option(help="Set subfolder inside vault for paper notes")] = "",
    obsidian_filename_pattern: Annotated[
        str,
        typer.Option(help="Set Obsidian note filename pattern (placeholders: {year}, {author}, {title})"),
    ] = "",
    obsidian_tag: Annotated[
        Optional[List[str]],
        typer.Option(
            "--obsidian-tag",
            help="Set Obsidian tags (repeatable, replaces existing list). E.g. --obsidian-tag paper --obsidian-tag science",
        ),
    ] = None,
    obsidian_wikilinks: Annotated[
        Optional[bool],
        typer.Option(
            "--obsidian-wikilinks/--no-obsidian-wikilinks",
            help="Use Obsidian [[wikilinks]] in generated notes",
        ),
    ] = None,
    # --- pedro ---
    pedro_fair_use: Annotated[
        Optional[bool],
        typer.Option(
            "--pedro-fair-use/--no-pedro-fair-use",
            help="Acknowledge PEDro fair-use policy to enable the source",
        ),
    ] = None,
    pedro_fetch_details: Annotated[
        Optional[bool],
        typer.Option(
            "--pedro-fetch-details/--no-pedro-fetch-details",
            help="Fetch each PEDro record page to get authors, year, DOI and abstract (slower)",
        ),
    ] = None,
    pedro_rate_limit_delay: Annotated[
        Optional[float],
        typer.Option(help="Set PEDro-specific rate-limit delay in seconds (default: 3.0)"),
    ] = None,
    # --- llm ---
    llm_provider: Annotated[
        str, typer.Option("--llm-provider", help='LLM provider for relevance ranking: "openai" or "anthropic"')
    ] = "",
    llm_api_key: Annotated[
        str, typer.Option("--llm-api-key", help="API key for the LLM provider (any string for local servers)")
    ] = "",
    llm_model: Annotated[
        str, typer.Option("--llm-model", help="Model name (leave empty for provider default)")
    ] = "",
    llm_base_url: Annotated[
        str, typer.Option("--llm-base-url", help="Base URL for a local OpenAI-compatible server (e.g. http://localhost:11434/v1)")
    ] = "",
    # --- rag / embeddings ---
    embedding_model: Annotated[
        str, typer.Option("--embedding-model", help="Embedding model name (e.g. snowflake-arctic-embed2, text-embedding-3-small)")
    ] = "",
    embedding_base_url: Annotated[
        str, typer.Option("--embedding-base-url", help="Base URL for the embedding server (e.g. http://localhost:11434/v1)")
    ] = "",
    embedding_api_key: Annotated[
        str, typer.Option("--embedding-api-key", help="API key for the embedding server (any string for local servers)")
    ] = "",
    rag_top_k: Annotated[
        Optional[int], typer.Option("--rag-top-k", help="Number of papers retrieved per RAG query (default: 10)")
    ] = None,
    rag_auto_index: Annotated[
        Optional[bool],
        typer.Option("--rag-auto-index/--no-rag-auto-index", help="Auto-index new papers after each search/get run")
    ] = None,
):
    """View or update MOSAIC configuration."""
    cfg = cfg_mod.load()

    # --- API keys ---
    api_keys_changed = apply_api_keys(
        cfg,
        {
            "elsevier_key": elsevier_key,
            "ss_key": ss_key,
            "ncbi_key": ncbi_key,
            "core_key": core_key,
            "ads_key": ads_key,
            "ieee_key": ieee_key,
            "springer_key": springer_key,
            "scopus_key": scopus_key,
            "scopus_inst_token": scopus_inst_token,
            "zenodo_key": zenodo_key,
        },
    )
    # PMC shares the NCBI key
    if ncbi_key:
        cfg["sources"]["pmc"]["api_key"] = ncbi_key
    if zotero_key:
        cfg["zotero"]["api_key"] = zotero_key
        from mosaic.zotero import ZoteroClient

        client = ZoteroClient(api_key=zotero_key)
        try:
            uid = client.discover_user_id()
            cfg["zotero"]["user_id"] = uid
            rprint(f"[green]Zotero web API configured for user {uid}[/green]")
        except Exception as e:
            warn(f"[dark_orange]Could not auto-discover Zotero user ID: {e}[/dark_orange]")
    if unpaywall_email:
        cfg["unpaywall"]["email"] = unpaywall_email

    # --- download / files ---
    if download_dir:
        cfg["download_dir"] = download_dir
    if db_path:
        cfg["db_path"] = db_path
    if filename_pattern:
        cfg["filename_pattern"] = filename_pattern
    if rate_limit_delay is not None:
        cfg["rate_limit_delay"] = rate_limit_delay

    # --- source enable/disable ---
    _sources_changed = False
    for name in enable_source or []:
        if name not in cfg_mod._KNOWN_SOURCES:
            rprint(f"[red]Unknown source: {name!r}. Known sources: {', '.join(sorted(cfg_mod._KNOWN_SOURCES))}[/red]")
            raise typer.Exit(1)
        cfg["sources"].setdefault(name, {})["enabled"] = True
        rprint(f"[green]Source '{name}' enabled.[/green]")
        _sources_changed = True
    for name in disable_source or []:
        if name not in cfg_mod._KNOWN_SOURCES:
            rprint(f"[red]Unknown source: {name!r}. Known sources: {', '.join(sorted(cfg_mod._KNOWN_SOURCES))}[/red]")
            raise typer.Exit(1)
        cfg["sources"].setdefault(name, {})["enabled"] = False
        rprint(f"[dark_orange]Source '{name}' disabled.[/dark_orange]")
        _sources_changed = True

    # --- obsidian ---
    _obsidian_changed = False
    if obsidian_vault:
        cfg["obsidian"]["vault_path"] = obsidian_vault
        _obsidian_changed = True
    if obsidian_subfolder:
        cfg["obsidian"]["subfolder"] = obsidian_subfolder
        _obsidian_changed = True
    if obsidian_filename_pattern:
        cfg["obsidian"]["filename_pattern"] = obsidian_filename_pattern
        _obsidian_changed = True
    if obsidian_tag is not None:
        cfg["obsidian"]["tags"] = obsidian_tag
        _obsidian_changed = True
    if obsidian_wikilinks is not None:
        cfg["obsidian"]["wikilinks"] = obsidian_wikilinks
        _obsidian_changed = True
    if _obsidian_changed:
        rprint("[green]Obsidian config updated.[/green]")

    # --- pedro ---
    if pedro_fair_use is not None:
        cfg["sources"]["pedro"]["acknowledge_fair_use"] = pedro_fair_use
        if pedro_fair_use:
            rprint("[green]PEDro fair-use policy acknowledged. Source is now enabled.[/green]")
        else:
            rprint("[dark_orange]PEDro fair-use acknowledgement removed. Source is now disabled.[/dark_orange]")
    if pedro_fetch_details is not None:
        cfg["sources"]["pedro"]["fetch_details"] = pedro_fetch_details
        if pedro_fetch_details:
            rprint("[green]PEDro detail fetching enabled (authors, year, DOI, abstract).[/green]")
        else:
            warn("[dark_orange]PEDro detail fetching disabled.[/dark_orange]")
    if pedro_rate_limit_delay is not None:
        cfg["sources"]["pedro"]["rate_limit_delay"] = pedro_rate_limit_delay

    # --- llm ---
    if llm_provider:
        cfg["llm"]["provider"] = llm_provider
    if llm_api_key:
        cfg["llm"]["api_key"] = llm_api_key
    if llm_model:
        cfg["llm"]["model"] = llm_model
    if llm_base_url:
        cfg["llm"]["base_url"] = llm_base_url
    _llm_changed = any([llm_provider, llm_api_key, llm_model, llm_base_url])
    if _llm_changed:
        rprint("[green]LLM config updated.[/green]")

    # --- rag ---
    _rag_changed = False
    if embedding_model:
        cfg["rag"]["embedding_model"] = embedding_model
        _rag_changed = True
    if embedding_base_url:
        cfg["rag"]["embedding_base_url"] = embedding_base_url
        _rag_changed = True
    if embedding_api_key:
        cfg["rag"]["embedding_api_key"] = embedding_api_key
        _rag_changed = True
    if rag_top_k is not None:
        cfg["rag"]["top_k"] = rag_top_k
        _rag_changed = True
    if rag_auto_index is not None:
        cfg["rag"]["auto_index"] = rag_auto_index
        _rag_changed = True
    if _rag_changed:
        rprint("[green]RAG config updated.[/green]")

    _pedro_changed = pedro_fair_use is not None or pedro_fetch_details is not None or pedro_rate_limit_delay is not None
    _any_changed = any(
        [
            api_keys_changed,
            zotero_key,
            unpaywall_email,
            download_dir,
            db_path,
            filename_pattern,
            rate_limit_delay is not None,
            _sources_changed,
            _obsidian_changed,
            _pedro_changed,
            _llm_changed,
            _rag_changed,
        ]
    )
    if _any_changed:
        cfg_mod.save(cfg)
        rprint("[green]Config saved to[/green] ~/.config/mosaic/config.toml")

    if show or not _any_changed:
        console.print_json(data=cfg)


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
        raise typer.Exit(1)

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
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _emit_json(
    papers: list,
    *,
    query: str = "",
    seed: str | None = None,
    errors: list[str] | None = None,
) -> None:
    """Serialise *papers* as a JSON object and print to stdout."""
    import dataclasses
    import json as _json

    def _paper_dict(p) -> dict:
        d = dataclasses.asdict(p)
        d["uid"] = p.uid
        return d

    result: dict = {
        "status": "ok",
        "query": query,
        "count": len(papers),
        "papers": [_paper_dict(p) for p in papers],
        "errors": errors or [],
    }
    if seed is not None:
        result["seed"] = seed
    print(_json.dumps(result, indent=2, default=str))


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
        rprint(f"[dark_orange]No DOIs found in {from_file.name}[/dark_orange]")
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
            _bare = Paper(title=doi, doi=doi, source="manual")
            paper = cache.get_by_uid(_bare.uid) or _bare
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
    per_source = stats.get("per_source", {})
    raw_total = stats.get("raw_total", 0)
    unique = stats.get("unique", 0)
    merged = stats.get("merged", 0)

    table = Table(
        show_header=True,
        header_style="cyan",
        box=box.SIMPLE,
        show_edge=False,
        title="[bold]Search stats[/bold]",
    )
    table.add_column("Source", min_width=20)
    table.add_column("Results", justify="right", no_wrap=True)

    for name, count in per_source.items():
        src_color = _RAINBOW[hash(name) % len(_RAINBOW)]
        label = f"[{src_color}]{name}[/{src_color}]"
        table.add_row(label, f"[cyan]{count}[/cyan]")

    table.add_section()
    table.add_row("[dim]Total raw[/dim]", f"[cyan]{raw_total}[/cyan]")
    table.add_row("[dim]Merged[/dim]",    f"[cyan]{merged}[/cyan]")
    table.add_row("[dim]Unique[/dim]",    f"[cyan]{unique}[/cyan]")

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
    if filter_parts:
        table.add_section()
        table.add_row("[dim]Filters[/dim]", f"[dim]{', '.join(filter_parts)}[/dim]")

    console.print(table)


def _post_process(
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
) -> None:
    """Shared post-processing: filter, export, download, push to Zotero/Obsidian."""
    if sort_by and sort_by not in ("citations", "year", "relevance"):
        rprint(f'[red]Unknown --sort value "{sort_by}". Use: citations, year, relevance[/red]')
        raise typer.Exit(1)
    non_relevance_sort = sort_by if sort_by != "relevance" else ""
    papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only, sort_by=non_relevance_sort)
    if sort_by == "relevance":
        papers = sort_by_relevance(query, papers, cfg)

    if not papers:
        rprint("[dark_orange]No results found.[/dark_orange]")
        raise typer.Exit()

    for p in papers:
        cache.save(p)

    _print_results(papers, show_relevance=sort_by == "relevance")

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

    # Auto-index if configured
    if cfg.get("rag", {}).get("auto_index") and papers:
        try:
            from mosaic.rag import index_papers
            index_papers(papers, cfg, cache, progress=False)
        except Exception:
            pass  # auto-index failures are always silent


_RAINBOW = ["red", "dark_orange", "green", "cyan", "blue", "magenta"]

_SORT_VALUES  = ["citations", "year", "relevance"]
_FIELD_VALUES = ["title", "abstract", "all"]
_AUTH_PROVIDERS = ["elsevier", "springer", "scopus"]


def _complete_session_names() -> list[str]:
    from mosaic.auth import list_sessions
    return [s["name"] for s in list_sessions()]


def _print_results(papers: list, show_relevance: bool = False) -> None:
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
        table.add_column("Rel.", width=6, justify="right")

    for i, p in enumerate(papers, 1):
        oa = "[green]yes[/green]" if p.is_open_access else "[red]no[/red]"
        pdf = "[green]✓[/green]" if p.pdf_url else "[dim]–[/dim]"
        doi = p.doi or "[dim]–[/dim]"
        color = _RAINBOW[(i - 1) % len(_RAINBOW)]
        src_color = _RAINBOW[hash(p.source) % len(_RAINBOW)]
        source = f"[{src_color}]{p.source}[/{src_color}]"
        row = [f"[{color}]{i}[/{color}]", p.title[:80], p.short_authors, str(p.year or ""), doi, source, oa, pdf]
        if show_citations:
            cited = str(p.citation_count) if p.citation_count is not None else "[dim]–[/dim]"
            row.append(cited)
        if show_relevance:
            rel = f"{p.relevance_score:.2f}" if p.relevance_score is not None else "[dim]–[/dim]"
            row.append(rel)
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
            "--field", "-f",
            help='Scope query to "title", "abstract", or "all" (default)',
            autocompletion=lambda: _FIELD_VALUES,
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
        warn(f"[dark_orange]Warning:[/dark_orange] {err}")

    papers = filter_papers(papers, oa_only=oa_only, pdf_only=pdf_only)

    if not papers:
        rprint("[dark_orange]No results found.[/dark_orange]")
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
    import asyncio

    from mosaic.auth import login as do_login

    asyncio.run(do_login(name, url))


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
        warn(f"[dark_orange]No session found for:[/dark_orange] {name}")


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


# ── mosaic cache subcommands ──────────────────────────────────────────────────

def _cache_and_cfg():
    cfg = cfg_mod.load()
    return Cache(cfg["db_path"]), cfg


@cache_app.command("stats")
def cache_stats() -> None:
    """Print a summary of the local cache."""
    cache, _ = _cache_and_cfg()
    s = cache.stats()
    mb = s["db_bytes"] / 1_048_576

    table = Table(show_header=False, box=box.SIMPLE, show_edge=False)
    table.add_column("Key",   style="dim", min_width=20)
    table.add_column("Value", justify="right")
    table.add_row("Papers cached",    f"[cyan]{s['papers']}[/cyan]")
    table.add_row("  with abstract",  f"[dim]{s['with_abstract']}[/dim]")
    table.add_row("  open access",    f"[dim]{s['open_access']}[/dim]")
    table.add_row("  with PDF URL",   f"[dim]{s['with_pdf_url']}[/dim]")
    table.add_row("Downloads (ok)",   f"[green]{s['downloaded']}[/green]")
    table.add_row("Searches logged",  f"[cyan]{s['searches']}[/cyan]")
    table.add_row("Exports tracked",  f"[cyan]{s['exports']}[/cyan]")
    table.add_row("DB size",          f"[dim]{mb:.2f} MB[/dim]")
    console.print(table)


@cache_app.command("list")
def cache_list(
    query: Annotated[str,  typer.Option("--query", "-q", help="Filter by title/abstract")] = "",
    limit: Annotated[int,  typer.Option("--limit", "-n", help="Max rows to show")] = 50,
    offset: Annotated[int, typer.Option("--offset",      help="Skip first N rows")] = 0,
) -> None:
    """List cached papers, newest first."""
    cache, _ = _cache_and_cfg()
    papers = cache.list_papers(limit=limit, offset=offset, query=query)
    total  = cache.count_papers(query=query)

    if not papers:
        rprint("[dim]No papers in cache.[/dim]")
        return

    table = Table(show_header=True, header_style="cyan", box=box.SIMPLE,
                  show_edge=False, expand=True)
    table.add_column("#",       width=5)
    table.add_column("Title",   min_width=30, ratio=3)
    table.add_column("Authors", ratio=2)
    table.add_column("Year",    width=6)
    table.add_column("Source",  width=16)
    table.add_column("OA",      width=4)
    table.add_column("PDF",     width=4)
    table.add_column("Abstr",   width=5)

    for i, p in enumerate(papers, offset + 1):
        color    = _RAINBOW[(i - 1) % len(_RAINBOW)]
        oa       = "[green]✓[/green]" if p.is_open_access else "[red]✗[/red]"
        pdf      = "[green]✓[/green]" if p.pdf_url        else "[dim]–[/dim]"
        abstract = "[green]✓[/green]" if p.abstract       else "[dim]–[/dim]"
        table.add_row(
            f"[{color}]{i}[/{color}]",
            p.title[:80],
            p.short_authors,
            str(p.year or ""),
            p.source,
            oa, pdf, abstract,
        )

    console.print(table)
    showing = offset + len(papers)
    console.print(f"[dim]Showing {offset + 1}–{showing} of {total}[/dim]")


@cache_app.command("show")
def cache_show(
    identifier: Annotated[
        str, typer.Argument(help="DOI, arXiv ID, or full UID of the paper")
    ],
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

    row("Title",          paper.title)
    row("Authors",        paper.short_authors)
    row("Year",           paper.year)
    row("DOI",            paper.doi)
    row("arXiv ID",       paper.arxiv_id)
    row("Journal",        paper.journal)
    row("Source",         paper.source)
    row("Open access",    "[green]yes[/green]" if paper.is_open_access else "no")
    row("PDF URL",        paper.pdf_url)
    row("Citation count", paper.citation_count)
    row("UID",            paper.uid)
    if paper.abstract:
        row("Abstract", paper.abstract[:300] + ("…" if len(paper.abstract) > 300 else ""))
    if dl:
        table.add_section()
        row("Local file",   dl["local_path"])
        row("Download status", dl["status"])
        row("Downloaded at",   dl["downloaded_at"])

    console.print(table)


@cache_app.command("verify")
def cache_verify() -> None:
    """Check that all tracked download files still exist on disk."""
    cache, _ = _cache_and_cfg()
    results = cache.verify_downloads()

    if not results:
        rprint("[dim]No completed downloads tracked.[/dim]")
        return

    ok      = [r for r in results if r["exists"]]
    missing = [r for r in results if not r["exists"]]

    rprint(f"[green]{len(ok)} file(s) OK[/green], [red]{len(missing)} missing[/red]")

    if missing:
        table = Table(show_header=True, header_style="cyan", box=box.SIMPLE, show_edge=False)
        table.add_column("UID",        style="dim")
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
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")
    ] = False,
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
    query: Annotated[
        str, typer.Option("--query", "-q", help="Filter by title/abstract")
    ] = "",
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Max papers to export (0 = all)")
    ] = 0,
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


if __name__ == "__main__":
    app()
