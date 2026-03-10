"""Fan-out search across all enabled sources with deduplication."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource


def _query_source(
    source: BaseSource,
    query: str,
    max_results: int,
    filters: SearchFilters | None,
) -> tuple[str, list[Paper]]:
    """Query a single source (runs inside a thread pool worker)."""
    return source.name, source.search(query, max_results=max_results, filters=filters)


def search_all(
    sources: list[BaseSource],
    query: str,
    max_per_source: int = 25,
    filters: SearchFilters | None = None,
    errors: list[str] | None = None,
    stats: dict | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
    parallel: bool = True,
) -> list[Paper]:
    seen: dict[str, Paper] = {}
    per_source: dict[str, int] = {}
    raw_total = 0
    merged = 0

    active = [s for s in sources if s.available()]

    if parallel and len(active) > 1:
        workers = min(len(active), 8)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_query_source, s, query, max_per_source, filters): s
                for s in active
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    name, results = future.result()
                    per_source[name] = len(results)
                    raw_total += len(results)
                    for paper in results:
                        _merge(seen, paper)
                    if progress_callback:
                        progress_callback(name, "done")
                except Exception as e:
                    if errors is not None:
                        errors.append(f"{source.name}: {e}")
                    if progress_callback:
                        progress_callback(source.name, "error")
    else:
        for source in active:
            try:
                results = source.search(query, max_results=max_per_source, filters=filters)
            except Exception as e:
                if errors is not None:
                    errors.append(f"{source.name}: {e}")
                if progress_callback:
                    progress_callback(source.name, "error")
                continue
            per_source[source.name] = len(results)
            raw_total += len(results)
            for paper in results:
                _merge(seen, paper)
            if progress_callback:
                progress_callback(source.name, "done")

    merged = raw_total - len(seen)
    papers = list(seen.values())

    # post-processing: safety net for sources that don't support native filtering
    if filters:
        papers = [p for p in papers if filters.match(p)]

    if stats is not None:
        stats["per_source"] = per_source
        stats["raw_total"] = raw_total
        stats["unique"] = len(seen)
        stats["merged"] = merged
        stats["after_filters"] = len(papers)

    return papers


def _merge(seen: dict[str, Paper], paper: Paper) -> None:
    uid = paper.uid
    if uid not in seen:
        seen[uid] = paper
        return
    existing = seen[uid]
    if paper.abstract and not existing.abstract:
        existing.abstract = paper.abstract
    if paper.pdf_url and not existing.pdf_url:
        existing.pdf_url = paper.pdf_url
    if paper.doi and not existing.doi:
        existing.doi = paper.doi
    if paper.citation_count is not None and (
        existing.citation_count is None
        or paper.citation_count > existing.citation_count
    ):
        existing.citation_count = paper.citation_count
