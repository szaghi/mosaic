"""Abstract base class for citation metadata providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mosaic.models import Paper


class BaseCitationProvider(ABC):
    """Fetches the reference list (outgoing citations) for a given paper.

    Providers are called in priority order by the enrichment orchestrator.
    Each provider returns a list of target UIDs in mosaic's canonical format
    (``doi:…``, ``arxiv:…``) so they can be matched against the local papers
    table.

    Implementing a new provider requires only two methods: ``can_handle`` to
    declare which papers are supported, and ``fetch_references`` to perform
    the actual lookup.  Both methods must be safe to call concurrently and
    must never raise — return an empty list on any error and log a warning.
    """

    name: str  # unique identifier stored in paper_citations.provider

    @abstractmethod
    def fetch_references(self, paper: Paper) -> list[str]:
        """Return mosaic UIDs of papers cited by *paper*.

        Args:
            paper: The paper whose outgoing reference list is requested.

        Returns:
            List of mosaic-canonical UIDs (e.g. ``"doi:10.1234/foo"``).
            Empty list when the paper is not found or references are
            unavailable.  Must never raise.
        """

    @abstractmethod
    def can_handle(self, paper: Paper) -> bool:
        """Return True if this provider can attempt to fetch references.

        Args:
            paper: Candidate paper.

        Returns:
            True when *paper* carries the identifiers required by this
            provider (e.g. a DOI or arXiv ID).
        """
