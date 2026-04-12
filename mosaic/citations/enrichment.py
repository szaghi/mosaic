"""Citation enrichment orchestrator — fetches and stores citation edges."""

from __future__ import annotations

import logging

from mosaic.citations.registry import build_citation_providers
from mosaic.db import Cache
from mosaic.models import Paper

_log = logging.getLogger(__name__)


def enrich_citations(
    papers: list[Paper],
    cfg: dict,
    cache: Cache,
    *,
    reindex: bool = False,
    progress: bool = True,
) -> tuple[int, int]:
    """Fetch citation edges for *papers* and store them in the local DB.

    For each candidate paper (not yet enriched unless ``reindex=True``),
    iterates configured providers in priority order and uses the first one
    that returns a non-empty reference list.  Only edges whose target UID is
    present in the local papers table are stored (dangling references to
    uncached papers are silently dropped).

    Note: papers that were queried but had no local citation matches are NOT
    tracked as "enriched" and will be re-attempted on the next run.  This is
    a deliberate simplification; a future improvement could add a separate
    attempt-tracking table.

    Args:
        papers: Papers to enrich.
        cfg: Loaded mosaic config dict.
        cache: Local SQLite cache.
        reindex: When True, re-fetch citations even for already-enriched papers.
        progress: Show a Rich progress bar.

    Returns:
        ``(enriched_count, skipped_count)`` where *enriched_count* is the
        number of papers for which at least one local citation edge was
        written, and *skipped_count* is the number of papers skipped because
        they were already enriched or no provider could handle them.
    """
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    providers = build_citation_providers(cfg)
    if not providers:
        _log.warning("enrich_citations: no citation providers configured")
        return 0, len(papers)

    already_enriched = set() if reindex else cache.get_enriched_uids()
    local_uids: set[str] = {p.uid for p in cache.get_all_papers()}

    candidates = [
        p
        for p in papers
        if p.uid not in already_enriched and any(prov.can_handle(p) for prov in providers)
    ]

    skipped = len(papers) - len(candidates)
    if not candidates:
        return 0, skipped

    provider_names = ", ".join(p.name for p in providers)

    if progress:
        prog = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            transient=True,
        )
        task = prog.add_task(
            f"[cyan]Enriching citations[/cyan] [dim]({provider_names})[/dim]",
            total=len(candidates),
        )
        prog.start()
    else:
        prog = None
        task = None

    enriched = 0
    try:
        for paper in candidates:
            for provider in providers:
                if not provider.can_handle(paper):
                    continue
                ref_uids = provider.fetch_references(paper)
                # Keep only edges whose target is in the local cache
                local_refs = [uid for uid in ref_uids if uid in local_uids]
                if local_refs:
                    edges = [(paper.uid, target, provider.name) for target in local_refs]
                    cache.upsert_citation_edges(edges)
                    enriched += 1
                    break  # first provider with local results wins
            if prog and task is not None:
                prog.advance(task)
    finally:
        if prog:
            prog.stop()

    _log.info(
        "Citation enrichment: %d enriched, %d skipped (no local matches or already done)",
        enriched,
        skipped + (len(candidates) - enriched),
    )
    return enriched, skipped
