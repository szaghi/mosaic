"""Library analysis: citation ``network`` and ``compare`` tables."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich import print as rprint
from rich.table import Table

import mosaic.config as cfg_mod
from mosaic.cli.app import app, console
from mosaic.cli.helpers import RAINBOW, open_cache, select_papers_or_exit

_COMPARE_SORT_VALUES = ["citations", "year"]


@app.command()
def network(
    query: Annotated[
        str, typer.Option("--query", "-q", help="Seed graph from cached papers matching this query")
    ] = "",
    depth: Annotated[
        int, typer.Option("--depth", help="Citation hops to follow from seed papers")
    ] = 2,
    min_connections: Annotated[
        int, typer.Option("--min-connections", help="Exclude papers with fewer edges than this")
    ] = 1,
    cluster: Annotated[
        bool, typer.Option("--cluster", help="Group papers into topic clusters")
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write graph to file (.json, .gv, .md)"),
    ] = None,
    top: Annotated[
        int, typer.Option("--top", help="Most-connected papers to show per cluster (terminal)")
    ] = 5,
) -> None:
    """Analyse the local citation network and visualise paper clusters.

    With no options, prints the most-connected papers across the full citation
    graph.  Use --query to start from a topic subset and --cluster to group
    results by community.  Export with --output to JSON (node-link), .gv
    (Graphviz DOT), or .md (Mermaid diagram).
    """
    from mosaic.network import export_graph
    from mosaic.services import analyse_network

    cfg = cfg_mod.load()
    cache = open_cache(cfg)

    try:
        graph = analyse_network(
            cache, query=query, depth=depth, min_connections=min_connections, cluster=cluster
        )
    except LookupError as e:
        rprint(f"[yellow]{e}[/yellow]")
        raise typer.Exit() from None

    nodes, adj, papers_map, clusters = (
        graph["nodes"],
        graph["adj"],
        graph["papers"],
        graph["clusters"],
    )

    # Write to file if requested
    if output:
        try:
            export_graph(nodes, adj, papers_map, output, clusters)
            rprint(f"[green]Graph written to:[/green] {output}")
        except ValueError as e:
            rprint(f"[red]{e}[/red]")
            raise typer.Exit(1) from None

    # Terminal report
    _print_network(nodes, adj, papers_map, clusters, graph["deg"], top)


def _print_network(
    nodes: set,
    adj: dict,
    papers_map: dict,
    clusters: list | None,
    deg: dict,
    top: int,
) -> None:
    """Render the network report to the terminal."""
    from rich.rule import Rule

    from mosaic.network import count_edges

    n_edges = count_edges(nodes, adj)
    console.print(
        f"\n[bold cyan]Citation Network[/bold cyan]  "
        f"[dim]{len(nodes)} papers · {n_edges} edges[/dim]\n"
    )

    if clusters:
        for i, comp in enumerate(clusters, 1):
            sorted_uids = sorted(comp, key=lambda uid: deg.get(uid, 0), reverse=True)
            max_deg = deg.get(sorted_uids[0], 0) if sorted_uids else 0

            sample = papers_map.get(sorted_uids[0]) if sorted_uids else None
            label = sample.title[:35] if sample else f"Cluster {i}"

            console.print(Rule(f"[bold]Cluster {i}[/bold] — {label} ({len(comp)} papers)"))

            tbl = Table(box=box.SIMPLE, show_header=False, show_edge=False, padding=(0, 1))
            tbl.add_column("Hub", width=4)
            tbl.add_column("Title", min_width=40)
            tbl.add_column("Authors", min_width=14)
            tbl.add_column("Year", width=6)
            tbl.add_column("", min_width=12, justify="right")

            for uid in sorted_uids[:top]:
                p = papers_map.get(uid)
                is_hub = deg.get(uid, 0) == max_deg and max_deg > 0
                hub_mark = "[bold cyan]Hub[/bold cyan]" if is_hub else ""
                title = p.title[:65] if p else uid
                authors = p.short_authors if p else ""
                year = str(p.year or "") if p else ""
                d_val = deg.get(uid, 0)
                tbl.add_row(hub_mark, title, authors, year, f"[dim]degree={d_val}[/dim]")

            console.print(tbl)
            if len(comp) > top:
                console.print(f"  [dim]… and {len(comp) - top} more paper(s)[/dim]\n")
    else:
        # No clustering: show top-N most connected papers
        sorted_nodes = sorted(nodes, key=lambda uid: deg.get(uid, 0), reverse=True)
        tbl = Table(
            show_header=True,
            header_style="cyan",
            box=box.SIMPLE,
            show_edge=False,
            expand=True,
        )
        tbl.add_column("#", width=4)
        tbl.add_column("Title", min_width=30, ratio=3)
        tbl.add_column("Authors", ratio=2)
        tbl.add_column("Year", width=6)
        tbl.add_column("Degree", width=8, justify="right")

        for i, uid in enumerate(sorted_nodes[:top], 1):
            p = papers_map.get(uid)
            color = RAINBOW[(i - 1) % len(RAINBOW)]
            tbl.add_row(
                f"[{color}]{i}[/{color}]",
                (p.title[:70] if p else uid),
                (p.short_authors if p else ""),
                str(p.year or "") if p else "",
                str(deg.get(uid, 0)),
            )

        console.print(tbl)
        if len(nodes) > top:
            console.print(f"[dim]Showing top {top} of {len(nodes)} papers by degree.[/dim]")


@app.command()
def compare(
    query: Annotated[
        str,
        typer.Option("--query", "-q", help="Filter papers from the cache by title/abstract"),
    ] = "",
    from_file: Annotated[
        Path | None,
        typer.Option("--from", help="Load papers from a .bib or .csv file"),
    ] = None,
    n: Annotated[int, typer.Option("--max", "-n", help="Maximum number of papers to compare")] = 20,
    dimensions: Annotated[
        str,
        typer.Option(
            "--dimensions",
            help="Comma-separated comparison axes (default: method,dataset,metric,result)",
        ),
    ] = "",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write table to file (.md, .csv, .json)"),
    ] = None,
    sort: Annotated[
        str,
        typer.Option(
            "--sort",
            help="Pre-sort papers before comparing: citations or year",
            autocompletion=lambda: _COMPARE_SORT_VALUES,
        ),
    ] = "",
) -> None:
    """Compare a set of papers across structured dimensions using an LLM.

    Papers are drawn from the local cache, optionally filtered by --query or
    loaded from a .bib/.csv file.  When an LLM is configured the dimensions
    (method, dataset, metric, result by default) are extracted from each
    paper's title and abstract.  Without an LLM, only metadata fields
    (year, source, journal, DOI) are populated.

    Examples::

        mosaic compare -q "diffusion models" --sort citations -n 15 --output comparison.md
        mosaic compare --from refs.bib --dimensions "method,dataset,BLEU,limitations"
    """
    from mosaic.compare import (
        DEFAULT_DIMENSIONS,
        compare_papers,
        format_csv,
        format_json_output,
        format_markdown,
    )

    if sort and sort not in _COMPARE_SORT_VALUES:
        rprint(f"[red]Unknown --sort value {sort!r}. Use: citations, year[/red]")
        raise typer.Exit(1)

    cfg = cfg_mod.load()
    cache = open_cache(cfg)

    # ── Gather papers (--query and --from combine) ────────────────────────────
    papers = select_papers_or_exit(cache, query=query, from_file=from_file)
    if papers is None:
        papers = cache.get_all_papers()

    if not papers:
        rprint("[yellow]No papers found. Run [bold]mosaic search[/bold] first.[/yellow]")
        raise typer.Exit()

    # ── Sort ──────────────────────────────────────────────────────────────────
    if sort == "citations":
        papers = sorted(papers, key=lambda p: p.citation_count or 0, reverse=True)
    elif sort == "year":
        papers = sorted(papers, key=lambda p: p.year or 0, reverse=True)

    papers = papers[:n]

    # ── Parse dimensions ──────────────────────────────────────────────────────
    dims = (
        [d.strip() for d in dimensions.split(",") if d.strip()]
        if dimensions.strip()
        else DEFAULT_DIMENSIONS
    )

    # ── Extract ───────────────────────────────────────────────────────────────
    llm_configured = bool(cfg.get("llm", {}).get("api_key") and cfg.get("llm", {}).get("provider"))
    if not llm_configured:
        rprint(
            "[dim]No LLM configured — populating metadata fields only. "
            "Use [bold]mosaic config --llm-provider ...[/bold] to enable LLM extraction.[/dim]"
        )

    compare_errors: list[str] = []
    rows = compare_papers(papers, dims, cfg, errors=compare_errors)
    for err in compare_errors:
        rprint(f"[dark_orange]Warning:[/dark_orange] {err}")

    # ── Output ────────────────────────────────────────────────────────────────
    if output:
        suffix = output.suffix.lower()
        if suffix in {".md", ".markdown"}:
            content = format_markdown(papers, rows, dims)
        elif suffix == ".csv":
            content = format_csv(papers, rows, dims)
        elif suffix == ".json":
            content = format_json_output(papers, rows, dims)
        else:
            rprint(f"[red]Unsupported output format {suffix!r} — use .md, .csv, or .json[/red]")
            raise typer.Exit(1)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        rprint(f"[green]Comparison table written to:[/green] {output}")

    # Always print terminal table
    _print_compare_table(papers, rows, dims)


def _print_compare_table(papers: list, rows: list, dims: list) -> None:
    """Render the comparison as a Rich table in the terminal."""
    tbl = Table(
        show_header=True,
        header_style="cyan",
        box=box.SIMPLE,
        show_edge=False,
        expand=True,
    )
    tbl.add_column("#", width=3)
    tbl.add_column("Title", min_width=20, ratio=2)
    tbl.add_column("Year", width=6)
    tbl.add_column("Authors", min_width=12, ratio=1)
    for dim in dims:
        tbl.add_column(dim.title(), min_width=10, ratio=1)

    for i, (p, row) in enumerate(zip(papers, rows, strict=False), 1):
        color = RAINBOW[(i - 1) % len(RAINBOW)]
        cells = [
            f"[{color}]{i}[/{color}]",
            p.title[:55],
            str(p.year or "–"),
            p.short_authors,
        ] + [row.get(d, "–")[:40] for d in dims]
        tbl.add_row(*cells)

    console.print(tbl)
    console.print(f"[dim]{len(papers)} paper(s) compared[/dim]")
