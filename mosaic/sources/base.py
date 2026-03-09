"""Abstract base class for all search sources."""
from __future__ import annotations
from abc import ABC, abstractmethod
from mosaic.models import Paper, SearchFilters


class BaseSource(ABC):
    name: str = ""

    @abstractmethod
    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
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
