"""Abstract base class for all search sources."""
from __future__ import annotations
from abc import ABC, abstractmethod
from mosaic.models import Paper, SearchFilters


class BaseSource(ABC):
    name: str = ""

    @abstractmethod
    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        """Search for papers matching query. Returns list of Paper objects."""
        ...

    def available(self) -> bool:
        """Return False if the source is misconfigured (e.g. missing API key)."""
        return True
