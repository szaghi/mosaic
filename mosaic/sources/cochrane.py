"""Cochrane Database of Systematic Reviews, via Europe PMC (issue #27).

Cochrane's own APIs need OAuth credentials issued on request, and automated
access to cochranelibrary.com is blocked and barred by Wiley's terms. Europe PMC
indexes the CDSR (ISSN 1469-493X) with DOIs and abstracts, so this source is a
Europe PMC search restricted to that journal, labelled and linked as Cochrane.
"""

from __future__ import annotations

from mosaic.models import Paper, SearchFilters
from mosaic.sources.europepmc import EuropePMCSource

CDSR_ISSN = "1469-493X"
_LIBRARY = "https://www.cochranelibrary.com/cdsr/doi/{doi}/full"


class CochraneSource(EuropePMCSource):
    name = "Cochrane"

    def _build_query(self, query: str, filters: SearchFilters | None) -> str:
        # Parenthesise so the restriction also binds a user raw_query with ORs.
        return f'({super()._build_query(query, filters)}) AND ISSN:"{CDSR_ISSN}"'

    def _parse(self, item: dict) -> Paper:
        paper = super()._parse(item)
        paper.journal = paper.journal or "Cochrane Database of Systematic Reviews"
        if paper.doi:
            paper.url = _LIBRARY.format(doi=paper.doi)
        return paper
