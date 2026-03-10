"""Fan-out search across all enabled sources with deduplication."""
from __future__ import annotations
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource


def search_all(
    sources: list[BaseSource],
    query: str,
    max_per_source: int = 25,
    filters: SearchFilters | None = None,
    errors: list[str] | None = None,
    stats: dict | None = None,
) -> list[Paper]:
    seen: dict[str, Paper] = {}
    per_source: dict[str, int] = {}
    raw_total = 0
    merged = 0

    for source in sources:
        if not source.available():
            continue
        try:
            results = source.search(query, max_results=max_per_source, filters=filters)
        except Exception as e:
            if errors is not None:
                errors.append(f"{source.name}: {e}")
            continue
        per_source[source.name] = len(results)
        raw_total += len(results)
        for paper in results:
            uid = paper.uid
            if uid not in seen:
                seen[uid] = paper
            else:
                merged += 1
                # merge: prefer richer data
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
