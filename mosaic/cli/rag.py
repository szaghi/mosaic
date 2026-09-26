"""RAG over the local library: ``index``, ``ask`` and ``chat``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich import print as rprint

import mosaic.config as cfg_mod
from mosaic.cli.app import app, console
from mosaic.cli.helpers import open_cache, select_papers_or_exit
from mosaic.services import RAG_MODES


@app.command()
def index(
    reindex: Annotated[
        bool, typer.Option("--reindex", help="Re-embed all papers, even already-indexed ones")
    ] = False,
    query: Annotated[
        str, typer.Option("--query", "-q", help="Embed only papers matching this query")
    ] = "",
    from_file: Annotated[
        Path | None, typer.Option("--from", help="Embed only papers from a .bib or .csv file")
    ] = None,
    batch_size: Annotated[
        int, typer.Option("--batch-size", help="Texts per embedding API call")
    ] = 96,
    enrich_citations: Annotated[
        bool,
        typer.Option(
            "--enrich-citations",
            help="Fetch citation edges from OpenAlex/CrossRef after embedding and store them for graph-boosted retrieval",
        ),
    ] = False,
):
    """Build or update the vector index for semantic search and RAG."""
    from mosaic.rag import index_papers

    cfg = cfg_mod.load()
    cache = open_cache(cfg)

    # Gather candidate papers (--query and --from combine)
    papers = select_papers_or_exit(cache, query=query, from_file=from_file)
    if papers is None:
        papers = cache.get_all_papers()

    if not papers:
        rprint("[yellow]No matching papers found in cache. Run some searches first.[/yellow]")
        raise typer.Exit()

    from mosaic import pdf as _pdf
    from mosaic.rag import NO_PYMUPDF_MESSAGE, index_health

    if cfg.get("rag", {}).get("full_text_index", True) and not _pdf.is_available():
        rprint(f"[yellow]Warning: {NO_PYMUPDF_MESSAGE}[/yellow]")

    rprint(f"[cyan]Indexing {len(papers)} papers…[/cyan]")
    try:
        newly, skipped, full_text = index_papers(
            papers, cfg, cache, reindex=reindex, batch_size=batch_size
        )
    except (ValueError, RuntimeError) as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        rprint(f"[red]Embedding request failed: {e}[/red]")
        raise typer.Exit(1) from None
    rprint(f"[green]Indexed {newly} new paper(s).[/green] {skipped} already indexed.")
    if full_text:
        rprint(f"  [dim]└─ {full_text} full-text (PDF), {newly - full_text} metadata-only[/dim]")

    # ── Citation enrichment ───────────────────────────────────────────────────
    if enrich_citations or cfg.get("rag", {}).get("citations", {}).get("enabled", False):
        from mosaic.citations.enrichment import enrich_citations as _enrich

        rprint(f"[cyan]Enriching citation graph for {len(papers)} papers…[/cyan]")
        try:
            n_enriched, n_skipped = _enrich(papers, cfg, cache, reindex=reindex)
            rprint(
                f"[green]Citation edges stored for {n_enriched} paper(s).[/green] "
                f"{n_skipped} skipped (already enriched or no local matches)."
            )
        except Exception as e:
            rprint(f"[yellow]Citation enrichment warning: {e}[/yellow]")

    for warning in index_health(cfg, cache):
        if warning != NO_PYMUPDF_MESSAGE:  # already reported above
            rprint(f"[yellow]Warning: {warning}[/yellow]")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Question or topic to analyse")],
    mode: Annotated[
        str, typer.Option("--mode", help="synthesis (default), gaps, compare, extract")
    ] = "synthesis",
    query: Annotated[
        str,
        typer.Option(
            "--query", "-q", help="Pre-filter: restrict to papers matching this FTS query"
        ),
    ] = "",
    from_file: Annotated[
        Path | None,
        typer.Option("--from", help="Pre-filter: restrict to papers from a .bib or .csv file"),
    ] = None,
    year: Annotated[
        str | None, typer.Option("--year", "-y", help="Year or range filter (e.g. 2020-2024)")
    ] = None,
    n: Annotated[
        int | None, typer.Option("-n", "--top", help="Override rag.top_k for this query")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write answer to file (.md or .json)")
    ] = None,
    show_sources: Annotated[
        bool, typer.Option("--show-sources", help="Print retrieved papers before the answer")
    ] = False,
):
    """Ask a question about your cached papers using RAG."""
    from rich.markdown import Markdown
    from rich.rule import Rule

    from mosaic.rag import ask as rag_ask
    from mosaic.services import format_answer

    if mode not in RAG_MODES:
        rprint(f"[red]Unknown mode {mode!r}. Choose from: {', '.join(sorted(RAG_MODES))}[/red]")
        raise typer.Exit(1)

    cfg = cfg_mod.load()
    cache = open_cache(cfg)

    # --query, --from and --year restrict the retrieval pool (all must match)
    subset = select_papers_or_exit(cache, query=query, from_file=from_file, year=year or "")
    pre_filter = None if subset is None else [p.uid for p in subset]

    console.print(Rule(f"[cyan]mosaic ask[/cyan] · mode: {mode}"))

    try:
        answer, papers = rag_ask(question, cfg, cache, mode=mode, k=n, pre_filter=pre_filter)
    except (ValueError, RuntimeError) as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    except httpx.HTTPError as e:
        rprint(f"[red]LLM/embedding request failed: {e}[/red]")
        raise typer.Exit(1) from None

    if show_sources:
        rprint(f"\n[bold]Sources retrieved ({len(papers)}):[/bold]")
        for i, p in enumerate(papers, 1):
            authors = ", ".join(p.authors[:2]) if p.authors else "Unknown"
            rprint(f"  [{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})")
        rprint()

    console.print(Markdown(answer))

    # References footer
    if papers:
        rprint("\n[bold]References[/bold]")
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:3]) if p.authors else "Unknown"
        if len(p.authors) > 3:
            authors += " et al."
        rprint(f"  [{i}] {p.title or 'Untitled'} — {authors}, {p.year or '?'}")

    if output:
        fmt = "json" if output.suffix.lower() == ".json" else "md"
        output.write_text(format_answer(question, mode, answer, papers, fmt), encoding="utf-8")
        rprint(f"[green]Answer saved to {output}[/green]")


@app.command()
def chat(
    query: Annotated[
        str,
        typer.Option("--query", "-q", help="Narrow retrieval pool to papers matching this query"),
    ] = "",
    from_file: Annotated[
        Path | None,
        typer.Option("--from", help="Narrow retrieval pool to papers from a .bib or .csv file"),
    ] = None,
    mode: Annotated[
        str, typer.Option("--mode", help="Default prompt mode: synthesis, gaps, compare, extract")
    ] = "synthesis",
    year: Annotated[
        str | None,
        typer.Option(
            "--year", "-y", help="Narrow retrieval pool by year or range (e.g. 2020-2024)"
        ),
    ] = None,
):
    """Interactive RAG chat session over your cached papers."""
    from rich.markdown import Markdown
    from rich.rule import Rule

    from mosaic.rag import chat_turn

    if mode not in RAG_MODES:
        rprint(f"[red]Unknown mode {mode!r}. Choose from: {', '.join(sorted(RAG_MODES))}[/red]")
        raise typer.Exit(1)

    cfg = cfg_mod.load()
    cache = open_cache(cfg)

    subset = select_papers_or_exit(cache, query=query, from_file=from_file, year=year or "")
    pre_filter = None if subset is None else [p.uid for p in subset]

    current_mode = mode
    history: list[dict] = []
    last_papers: list = []  # papers retrieved for the most recent question

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
            if cmd == "/clear":
                history.clear()
                last_papers.clear()
                rprint("[dim]Conversation history cleared.[/dim]")
            elif cmd == "/mode":
                if arg in RAG_MODES:
                    current_mode = arg
                    rprint(f"[dim]Mode set to {current_mode}.[/dim]")
                else:
                    rprint(f"[red]Unknown mode. Choose from: {', '.join(sorted(RAG_MODES))}[/red]")
            elif cmd == "/sources":
                if not last_papers:
                    rprint("[dim]No sources yet — ask a question first.[/dim]")
                else:
                    for i, p in enumerate(last_papers, 1):
                        authors = ", ".join(p.authors[:2]) if p.authors else "Unknown"
                        rprint(f"  [{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})")
            else:
                rprint(f"[red]Unknown command: {cmd}[/red]")
            continue

        try:
            answer, papers = chat_turn(
                user_input, list(history), cfg, cache, mode=current_mode, pre_filter=pre_filter
            )
        except Exception as e:
            rprint(f"[red]Error: {e}[/red]")
            continue

        if papers:
            last_papers = papers
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": answer})

        rprint("\n[bold cyan]mosaic:[/bold cyan]")
        console.print(Markdown(answer))
        rprint()
