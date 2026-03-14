"""Shared business logic used by both the CLI and the web UI."""

from __future__ import annotations

from mosaic.models import Paper, SearchFilters


def build_filters(
    year: str = "",
    author: str | list[str] = "",
    journal: str = "",
    field: str = "all",
    raw_query: str = "",
) -> tuple[SearchFilters | None, str | None]:
    """Build a ``SearchFilters`` from user input.

    Args:
        year: Year string (``"2020"``, ``"2020-2024"``, or ``"2020,2022,2024"``).
        author: Comma-separated author string **or** a list of author names.
        journal: Journal name substring.
        field: ``"title"``, ``"abstract"``, or ``"all"``.
        raw_query: Raw query override.

    Returns:
        A tuple ``(filters_or_None, warning_or_None)``.  The warning is set
        when the year string cannot be parsed; other fields are still applied.
    """
    # Normalise author to a list
    if isinstance(author, str):
        authors = [a.strip() for a in author.split(",") if a.strip()] if author else []
    else:
        authors = list(author)

    if not any([year, authors, journal, field != "all", raw_query]):
        return None, None

    filters = SearchFilters(authors=authors, journal=journal, field=field, raw_query=raw_query)
    warning: str | None = None

    if year:
        try:
            parsed = SearchFilters.parse_year(year)
            filters.year_from = parsed.year_from
            filters.year_to = parsed.year_to
            filters.years = parsed.years
        except ValueError:
            warning = f'Invalid year format "{year}". Use: 2020, 2020-2024, or 2020,2022,2024'

    return filters, warning


def filter_papers(
    papers: list[Paper],
    *,
    oa_only: bool = False,
    pdf_only: bool = False,
    sort_by: str = "",
) -> list[Paper]:
    """Apply post-processing filters to a list of papers.

    Args:
        papers: Papers to filter (not mutated; a new list is returned).
        oa_only: Keep only open-access papers (or those with a PDF URL).
        pdf_only: Keep only papers that have a PDF URL.
        sort_by: ``"citations"`` (most cited first) or ``"year"`` (newest first).

    Returns:
        A filtered (and optionally sorted) list of papers.
    """
    result = list(papers)
    if oa_only:
        result = [p for p in result if p.is_open_access or p.pdf_url]
    if pdf_only:
        result = [p for p in result if p.pdf_url]
    if sort_by == "citations":
        result.sort(key=lambda p: p.citation_count or 0, reverse=True)
    elif sort_by == "year":
        result.sort(key=lambda p: p.year or 0, reverse=True)
    return result


def merge_papers(seen: dict[str, Paper], paper: Paper) -> None:
    """Merge *paper* into *seen*, preferring richer metadata.

    If a paper with the same ``uid`` already exists, missing fields on the
    existing record are filled in from *paper*.  Citation counts are updated
    only when the new count is higher.
    """
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
        existing.citation_count is None or paper.citation_count > existing.citation_count
    ):
        existing.citation_count = paper.citation_count
