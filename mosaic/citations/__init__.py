"""Citation graph enrichment for the local RAG pipeline."""

from mosaic.citations.base import BaseCitationProvider
from mosaic.citations.crossref import CrossRefCitationProvider
from mosaic.citations.enrichment import enrich_citations
from mosaic.citations.openalex import OpenAlexCitationProvider
from mosaic.citations.opencitations import OpenCitationsCitationProvider
from mosaic.citations.registry import build_citation_providers

__all__ = [
    "BaseCitationProvider",
    "CrossRefCitationProvider",
    "OpenAlexCitationProvider",
    "OpenCitationsCitationProvider",
    "build_citation_providers",
    "enrich_citations",
]
