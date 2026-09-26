"""Finding and fetching papers: ``search``, ``similar``, ``get`` and ``cite``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import mosaic.config as cfg_mod
from mosaic.cli.app import app, console, err_console, warn
from mosaic.cli.helpers import (
    FIELD_VALUES,
    RAINBOW,
    SORT_VALUES,
    export_outputs,
    finish_results,
    open_cache,
    push_obsidian,
    push_zotero,
    read_dois_or_exit,
    run_auto_index,
)
from mosaic.db import Cache
from mosaic.search import search_all
from mosaic.services import FIELD_CHOICES, SORT_CHOICES, build_filters
from mosaic.source_registry import SRC_MAP, build_sources, source_choices
from mosaic.workflows import finalize_search


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
    require_year: Annotated[
        bool,
        typer.Option(
            "--require-year",
            help="With --year, drop papers whose publication year is unknown (kept by default)",
        ),
    ] = False,
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
            autocompletion=lambda: SORT_VALUES,
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
    semantic: Annotated[
        bool,
        typer.Option(
            "--semantic",
            help="Search the local vector index by meaning instead of keywords (requires 'mosaic index' to have been run)",
        ),
    ] = False,
    downloaded_only: Annotated[
        bool,
        typer.Option(
            "--downloaded-only",
            help="Limit results to papers with a locally downloaded PDF (only with --cached or --semantic)",
        ),
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
    cache = open_cache(cfg)

    if field not in FIELD_CHOICES:
        rprint('[red]--field must be "title", "abstract", or "all"[/red]')
        raise typer.Exit(1)
    if sort_by and sort_by not in SORT_CHOICES:
        rprint(f'[red]Unknown --sort value "{sort_by}". Use: citations, year, relevance[/red]')
        raise typer.Exit(1)

    filters, year_warning = build_filters(
        year=year,
        author=list(author),
        journal=journal,
        field=field,
        raw_query=raw_query,
        require_year=require_year,
    )
    if year_warning:
        rprint(f"[red]{year_warning}[/red]")
        raise typer.Exit(1)

    history = {
        "filters": {
            "year": year,
            "author": ", ".join(author),
            "journal": journal,
            "field": field,
            "raw_query": raw_query,
        }
    }
    post_opts = {
        "output": list(output),
        "do_download": download,
        "oa_only": oa_only,
        "pdf_only": pdf_only,
        "zotero": zotero,
        "zotero_collection": zotero_collection,
        "zotero_local": zotero_local,
        "obsidian": obsidian,
        "obsidian_folder": obsidian_folder,
    }

    if cached or semantic:
        mode = "semantic" if semantic else "cached"
        history["filters"]["mode"] = mode
        history["sources"] = [mode]
        effective_sort = sort_by
        if semantic:
            if not json_output:
                rprint(f"[dim]Searching local vector index for '{query}'…[/dim]")
            try:
                from mosaic.rag import semantic_search

                papers = semantic_search(
                    query, cache, cfg, k=max_results, downloaded_only=downloaded_only
                )
            except RuntimeError as e:
                rprint(f"[red]{e}[/red]")
                raise typer.Exit(1) from None
            except ValueError as e:
                rprint(f"[red]{e}[/red]")
                rprint(
                    "[dim]Hint: run mosaic config --embedding-model <model> to configure an embedding model.[/dim]"
                )
                raise typer.Exit(1) from None
            # --sort citations/year is allowed; --sort relevance would clobber
            # semantic ordering with BM25, so treat it as no sort.
            effective_sort = sort_by if sort_by in ("citations", "year") else ""
        else:
            if not json_output:
                rprint(f"[dim]Searching local cache for '{query}'…[/dim]")
            papers = cache.search_local(query)
            if downloaded_only:
                dld = cache.get_downloaded_uids()
                papers = [p for p in papers if p.uid in dld]
        if filters:
            papers = [p for p in papers if filters.match(p)]
        if json_output:
            papers = finalize_search(
                papers,
                cfg,
                cache,
                query=query,
                oa_only=oa_only,
                pdf_only=pdf_only,
                sort_by=effective_sort,
                save=False,
                history=history,
            )
            export_outputs(papers, list(output), quiet=True)
            _emit_json(papers, query=query)
            return
        finish_results(
            papers,
            cfg,
            cache,
            query=query,
            sort_by=effective_sort,
            show_score=semantic,
            save=False,
            history=history,
            **post_opts,
        )
        return

    sources = build_sources(cfg)

    # filter by source shorthand (custom sources are selectable by name)
    if source:
        choices = source_choices(cfg)
        key = source.lower()
        if key not in choices:
            rprint(f"[red]Unknown source '{source}'. Use: {', '.join(choices)}[/red]")
            raise typer.Exit(1)
        name = choices[key]
        sources = [s for s in sources if s.name == name]
        if not sources:
            rprint(
                f"[dark_orange]Source '{source}' is not active (missing API key or disabled in config).[/dark_orange]"
            )
            raise typer.Exit(1)
    history["sources"] = sorted(s.name for s in sources)

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

    if json_output:
        papers = finalize_search(
            papers,
            cfg,
            cache,
            query=query,
            oa_only=oa_only,
            pdf_only=pdf_only,
            sort_by=sort_by,
            prefer_cache=prefer_cache,
            history=history,
        )
        export_outputs(papers, list(output), quiet=True)
        _emit_json(papers, query=query, errors=errors)
        return

    for err in errors:
        warn(f"[dark_orange]Warning:[/dark_orange] {err}")

    if stats:
        _print_search_stats(search_stats, filters)

    finish_results(
        papers,
        cfg,
        cache,
        query=query,
        sort_by=sort_by,
        prefer_cache=prefer_cache,
        history=history,
        **post_opts,
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
            autocompletion=lambda: SORT_VALUES,
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
    cache = open_cache(cfg)

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

            print(
                _json.dumps(
                    {"status": "error", "query": identifier, "errors": ["Paper not found"]},
                    indent=2,
                )
            )
            raise typer.Exit(1)
        rprint(f"[red]Paper not found:[/red] {identifier}")
        rprint("[dim]Check that the DOI or arXiv ID is correct.[/dim]")
        raise typer.Exit(1)

    if json_output:
        try:
            papers = finalize_search(
                papers,
                cfg,
                cache,
                query=seed_title or identifier,
                oa_only=oa_only,
                pdf_only=pdf_only,
                sort_by=sort_by,
            )
        except ValueError as e:
            err_console.print(f"[red]{e}[/red]")
            raise typer.Exit(1) from None
        export_outputs(papers, list(output), quiet=True)
        _emit_json(papers, query=identifier, seed=seed_title)
        return

    rprint(f"[bold]Similar to:[/bold] {seed_title}\n")

    finish_results(
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
    cache = open_cache(cfg)

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

    from mosaic.services import papers_for_dois
    from mosaic.workflows import download_papers

    paper = papers_for_dois(cache, [doi])[0]
    if paper.source != "manual":
        rprint(f"[dim]Found in local cache: {paper.title[:80]}[/dim]")
    report = download_papers([paper], cfg, cache, skip_without_link=False)
    path = report.items[0].path
    if path:
        rprint(f"[green]Saved:[/green] {path}")
    else:
        rprint("[red]Could not find a downloadable PDF for this DOI.[/red]")

    if zotero:
        push_zotero(
            [paper],
            cfg,
            collection_name=zotero_collection,
            force_local=zotero_local,
            pdf_map=report.pdf_map,
        )

    if obsidian:
        push_obsidian([paper], cfg, subfolder_override=obsidian_folder)

    run_auto_index([paper], cfg, cache)


_CITE_STYLES = ["bibtex", "apa", "mla", "chicago", "harvard", "vancouver"]


@app.command()
def cite(
    doi: Annotated[str, typer.Argument(help="DOI of the paper (e.g. 10.48550/arXiv.1706.03762)")],
    style: Annotated[
        str,
        typer.Option(
            "--style",
            "-s",
            help="Citation style: bibtex (default), apa, mla, chicago, harvard, vancouver",
            autocompletion=lambda: _CITE_STYLES,
        ),
    ] = "bibtex",
    copy: Annotated[
        bool,
        typer.Option("--copy", "-c", help="Copy the formatted citation to the clipboard"),
    ] = False,
):
    """Format and print a citation for a paper by DOI.

    Checks the local cache first; falls back to Crossref for unknown DOIs.
    BibTeX is rendered locally from stored metadata. All other styles use
    the Crossref content-negotiation endpoint (doi.org) — network required.
    """
    import httpx as _httpx

    from mosaic.cite import (
        SUPPORTED_STYLES,
        bibtex_citation,
        copy_to_clipboard,
        fetch_formatted_citation,
        resolve_paper,
    )
    from mosaic.parsing import normalise_doi

    style = style.lower()
    if style not in SUPPORTED_STYLES:
        rprint(f"[red]Unknown style '{style}'. Supported: {', '.join(SUPPORTED_STYLES)}[/red]")
        raise typer.Exit(1) from None

    cfg = cfg_mod.load()
    cache = open_cache(cfg)
    email = cfg.get("unpaywall", {}).get("email", "")

    bare_doi = normalise_doi(doi)
    if not bare_doi:
        rprint(f"[red]Could not parse DOI: {doi!r}[/red]")
        raise typer.Exit(1) from None

    try:
        if style == "bibtex":
            paper = resolve_paper(bare_doi, cache, email)
            citation_text = bibtex_citation(paper)
        else:
            citation_text = fetch_formatted_citation(bare_doi, style, email)
    except _httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            rprint(f"[red]DOI not found: {bare_doi}[/red]")
        else:
            rprint(f"[red]HTTP error {exc.response.status_code} fetching DOI {bare_doi}[/red]")
        raise typer.Exit(1) from None
    except _httpx.ConnectError:
        rprint("[red]Network unavailable — could not reach Crossref.[/red]")
        raise typer.Exit(1) from None
    except _httpx.TimeoutException:
        rprint("[red]Request timed out — Crossref did not respond in time.[/red]")
        raise typer.Exit(1) from None

    print(citation_text)

    if copy:
        ok = copy_to_clipboard(citation_text)
        if ok:
            rprint("[dim]Copied to clipboard.[/dim]")
        else:
            rprint("[yellow]Warning: clipboard unavailable — output printed above.[/yellow]")


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
    from mosaic.workflows import bulk_get

    dois = read_dois_or_exit(from_file)
    if not dois:
        rprint(f"[dark_orange]No DOIs found in {from_file.name}[/dark_orange]")
        raise typer.Exit()

    rprint(f"[dim]Found {len(dois)} DOI(s) in {from_file.name}[/dim]")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=False
    ) as prog:
        task_ids: list = []

        def _start(paper) -> None:
            task_ids.append(prog.add_task(f"{paper.doi}…"))

        def _done(item) -> None:
            prog.remove_task(task_ids.pop())
            if item.status == "ok":
                rprint(f"  [green]✓[/green] {Path(item.path).name}")
            elif oa_only:
                rprint(f"  [dim]–[/dim] {item.paper.doi} (no OA copy)")
            else:
                rprint(f"  [red]✗[/red] {item.paper.doi}")

        papers_list, report = bulk_get(dois, cfg, cache, on_start=_start, on_item=_done)

    ok, failed = report.count("ok"), report.count("fail")
    parts = [f"[bold]{ok}[/bold] downloaded"]
    if failed and oa_only:
        parts.append(f"[dim]{failed} skipped (no OA copy)[/dim]")
    elif failed:
        parts.append(f"[red]{failed} failed[/red]")
    console.print(f"\n[bold]Done:[/bold] {', '.join(parts)}")

    if zotero and papers_list:
        push_zotero(
            papers_list,
            cfg,
            collection_name=zotero_collection,
            force_local=zotero_local,
            pdf_map=report.pdf_map,
        )

    if obsidian and papers_list:
        push_obsidian(papers_list, cfg, subfolder_override=obsidian_folder)

    run_auto_index(papers_list, cfg, cache)


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
        src_color = RAINBOW[hash(name) % len(RAINBOW)]
        label = f"[{src_color}]{name}[/{src_color}]"
        table.add_row(label, f"[cyan]{count}[/cyan]")

    table.add_section()
    table.add_row("[dim]Total raw[/dim]", f"[cyan]{raw_total}[/cyan]")
    table.add_row("[dim]Merged[/dim]", f"[cyan]{merged}[/cyan]")
    table.add_row("[dim]Unique[/dim]", f"[cyan]{unique}[/cyan]")

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
