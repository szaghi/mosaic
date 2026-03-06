"""arXiv API source (no auth required, all OA)."""
from __future__ import annotations
import time
import xml.etree.ElementTree as ET
import httpx
from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_BASE = "https://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivSource(BaseSource):
    name = "arXiv"

    def __init__(self, delay: float = 3.0):
        self._delay = delay
        self._last_call = 0.0

    def search(self, query: str, max_results: int = 25, filters: SearchFilters | None = None) -> list[Paper]:
        elapsed = time.time() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        if filters and filters.raw_query:
            search_query = filters.raw_query
        elif filters and filters.field == "title":
            search_query = f"ti:{query}"
        elif filters and filters.field == "abstract":
            search_query = f"abs:{query}"
        else:
            search_query = f"all:{query}"
        if filters:
            if filters.authors:
                for author in filters.authors:
                    search_query += f" AND au:{author}"
            if filters.journal:
                search_query += f" AND jr:{filters.journal}"
            # date range: submittedDate:[YYYYMMDDtttt TO YYYYMMDDtttt]
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                d_from = f"{y_from or '0000'}01010000"
                d_to   = f"{y_to   or '9999'}12312359"
                search_query += f" AND submittedDate:[{d_from} TO {d_to}]"

        resp = httpx.get(_BASE, params={
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
        }, timeout=30)
        self._last_call = time.time()
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        papers = []
        for entry in root.findall("atom:entry", _NS):
            papers.append(self._parse(entry))
        return papers

    def _parse(self, entry: ET.Element) -> Paper:
        def txt(tag: str) -> str | None:
            el = entry.find(tag, _NS)
            return el.text.strip() if el is not None and el.text else None

        arxiv_id = (txt("atom:id") or "").split("/abs/")[-1]
        authors = [
            a.findtext("atom:name", namespaces=_NS) or ""
            for a in entry.findall("atom:author", _NS)
        ]
        published = txt("atom:published") or ""
        year = int(published[:4]) if published else None

        pdf_url = None
        for link in entry.findall("atom:link", _NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")

        doi_el = entry.find("arxiv:doi", _NS)
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

        journal_el = entry.find("arxiv:journal_ref", _NS)
        journal = journal_el.text.strip() if journal_el is not None and journal_el.text else None

        return Paper(
            title=txt("atom:title") or "",
            authors=[a for a in authors if a],
            year=year,
            doi=doi,
            arxiv_id=arxiv_id,
            abstract=txt("atom:summary"),
            journal=journal,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=True,
            url=f"https://arxiv.org/abs/{arxiv_id}",
        )
