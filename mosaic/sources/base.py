"""Abstract base class for all search sources and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mosaic.models import Paper, SearchFilters


class BaseSource(ABC):
    name: str = ""

    @abstractmethod
    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
        """Search for papers matching a query string.

        Args:
            query: Free-text search query.
            max_results: Maximum number of Paper objects to return.
            filters: Optional structured filters (year, author, journal, field,
                raw_query) that narrow or override the query.

        Returns:
            A list of Paper objects matching the query.
        """
        ...

    def available(self) -> bool:
        """Return False if the source is misconfigured (e.g. missing API key)."""
        return True


# ---------------------------------------------------------------------------
# Shared helpers for source implementations
# ---------------------------------------------------------------------------


def extract_year_range(filters: SearchFilters | None) -> tuple[int | None, int | None]:
    """Extract ``(year_from, year_to)`` from filters, coalescing an explicit years list.

    Returns:
        A tuple ``(year_from, year_to)`` where either or both may be ``None``.
    """
    if filters is None:
        return None, None
    y_from = filters.year_from or (min(filters.years) if filters.years else None)
    y_to = filters.year_to or (max(filters.years) if filters.years else None)
    return y_from, y_to


def build_field_query(
    query: str,
    filters: SearchFilters | None,
    title_prefix: str,
    abstract_prefix: str,
    default_prefix: str = "",
) -> str:
    """Build a field-scoped query string from filters.

    If ``filters.raw_query`` is set it is returned verbatim.  Otherwise the
    query is prefixed according to ``filters.field``.

    Args:
        query: The original user query.
        filters: Optional filters (may be ``None``).
        title_prefix: Format string applied for title scoping (e.g. ``'ti:{}'``).
            Use ``{}`` as placeholder for *query*.
        abstract_prefix: Format string for abstract scoping (e.g. ``'abs:{}'``).
        default_prefix: Format string used when no field scoping is active.
            Defaults to bare *query* (``""``).

    Returns:
        The scoped query string.
    """
    if filters and filters.raw_query:
        return filters.raw_query
    if filters and filters.field == "title":
        return title_prefix.format(query)
    if filters and filters.field == "abstract":
        return abstract_prefix.format(query)
    if default_prefix:
        return default_prefix.format(query)
    return query


def build_scopus_query(query: str, filters: SearchFilters | None) -> str:
    """Build a Scopus boolean query string from *query* and *filters*.

    Shared by both ``ScopusAPISource`` and ``ScopusBrowserSource`` to prevent
    drift between the two implementations.

    Returns:
        A Scopus advanced-search query string.
    """
    if filters and filters.raw_query:
        scopus_query = filters.raw_query
    elif filters and filters.field == "title":
        scopus_query = f'TITLE("{query}")'
    elif filters and filters.field == "abstract":
        scopus_query = f'ABS("{query}")'
    else:
        scopus_query = f'TITLE-ABS-KEY("{query}")'

    if filters:
        y_from, y_to = extract_year_range(filters)
        if y_from:
            scopus_query += f" AND PUBYEAR > {y_from - 1}"
        if y_to:
            scopus_query += f" AND PUBYEAR < {y_to + 1}"
        if filters.authors:
            for author in filters.authors:
                scopus_query += f' AND AUTH("{author}")'
        if filters.journal:
            scopus_query += f' AND SRCTITLE("{filters.journal}")'
    return scopus_query
