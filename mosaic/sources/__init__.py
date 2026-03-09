from mosaic.sources.arxiv import ArxivSource
from mosaic.sources.semantic_scholar import SemanticScholarSource
from mosaic.sources.sciencedirect import ScienceDirectSource
from mosaic.sources.sciencedirect_browser import ScienceDirectBrowserSource
from mosaic.sources.springer_browser import SpringerBrowserSource
from mosaic.sources.doaj import DoajSource
from mosaic.sources.europepmc import EuropePMCSource
from mosaic.sources.openalex import OpenAlexSource
from mosaic.sources.base_search import BASESource
from mosaic.sources.core import CORESource
from mosaic.sources.custom import CustomSource

__all__ = [
    "ArxivSource",
    "SemanticScholarSource",
    "ScienceDirectSource",
    "ScienceDirectBrowserSource",
    "SpringerBrowserSource",
    "DoajSource",
    "EuropePMCSource",
    "OpenAlexSource",
    "BASESource",
    "CORESource",
    "CustomSource",
]
