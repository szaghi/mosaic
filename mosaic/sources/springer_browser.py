"""Springer Nature browser-based search (no credentials required).

Springer's search results are fully JS-rendered, so an httpx request
returns no articles. A headless browser is required, but no login
session is needed — the search interface is publicly accessible.

Uses Firefox headless (preferred via _HEADLESS_PREFERENCE).
"""
from __future__ import annotations
import asyncio
import math
import re
from urllib.parse import urlencode

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_SP_BASE = "https://link.springer.com"
_SEARCH_URL = f"{_SP_BASE}/search"
_PAGE_SIZE = 20  # Springer returns 20 results per page


class SpringerBrowserSource(BaseSource):
    """Search Springer Nature via headless browser (no API key or session required)."""

    name = "Springer"

    def available(self) -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def search(self, query: str, max_results: int = 25,
               filters: SearchFilters | None = None) -> list[Paper]:
        try:
            from mosaic.auth import _require_playwright
            _require_playwright()
            return asyncio.run(self._browser_search(query, max_results, filters))
        except Exception:
            return []

    # ── async internals ───────────────────────────────────────────────────────

    async def _browser_search(self, query: str, max_results: int,
                               filters: SearchFilters | None) -> list[Paper]:
        from mosaic.auth import _launch_browser
        from playwright.async_api import async_playwright

        pages_needed = math.ceil(max_results / _PAGE_SIZE)
        papers: list[Paper] = []

        async with async_playwright() as p:
            browser = await _launch_browser(p, headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                for page_num in range(1, pages_needed + 1):
                    url = self._build_url(query, filters, page_num)
                    await page.goto(url, wait_until="networkidle", timeout=30_000)
                    try:
                        await page.wait_for_selector("li.app-card-open", timeout=10_000)
                    except Exception:
                        break
                    batch = await self._extract_results(page, max_results - len(papers))
                    papers.extend(batch)
                    if len(batch) < _PAGE_SIZE or len(papers) >= max_results:
                        break
            except Exception:
                pass
            finally:
                await browser.close()
        return papers

    def _build_url(self, query: str, filters: SearchFilters | None,
                   page: int) -> str:
        field = (filters.field or "all") if filters else "all"

        params: dict = {
            "search-within": "Article",
            "sortBy": "relevance",
        }
        if field == "title":
            params["title"] = query
        else:
            params["query"] = query

        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                params["date"] = "custom"
                params["dateFrom"] = y_from or y_to
                params["dateTo"]   = y_to or y_from
            if filters.journal:
                params["query"] = (params.get("query", "") + f" {filters.journal}").strip()

        if page > 1:
            params["page"] = page

        return f"{_SEARCH_URL}?{urlencode(params)}"

    async def _extract_results(self, page, max_results: int) -> list[Paper]:
        items = await page.query_selector_all("li.app-card-open")
        papers = []
        for item in items[:max_results]:
            try:
                paper = await self._parse_item(item)
                if paper:
                    papers.append(paper)
            except Exception:
                continue
        return papers

    async def _parse_item(self, item) -> Paper | None:
        # ── title + URL ───────────────────────────────────────────────────────
        title_el = await item.query_selector("[data-test=title] a")
        if not title_el:
            return None
        title = (await title_el.inner_text()).strip()
        if not title:
            return None

        href = await title_el.get_attribute("href") or ""
        article_url = f"{_SP_BASE}{href}" if href.startswith("/") else href or None

        # ── DOI (encoded in the article path) ────────────────────────────────
        doi: str | None = None
        m = re.search(r"10\.\d{4,}/\S+", href)
        if m:
            doi = m.group(0).rstrip(".,)")

        # ── authors ───────────────────────────────────────────────────────────
        authors: list[str] = []
        authors_el = await item.query_selector("[data-test=authors]")
        if authors_el:
            raw = (await authors_el.inner_text()).strip()
            # Strip trailing "..." and split on ", "
            raw = re.sub(r"\s*\.\.\.\s*$", "", raw)
            authors = [a.strip() for a in raw.split(",") if a.strip()]

        # ── journal ───────────────────────────────────────────────────────────
        journal: str | None = None
        journal_el = await item.query_selector("[data-test=parent]")
        if journal_el:
            journal = (await journal_el.inner_text()).strip() or None

        # ── year ──────────────────────────────────────────────────────────────
        year: int | None = None
        date_el = await item.query_selector("[data-test=published]")
        if date_el:
            date_text = (await date_el.inner_text()).strip()
            y_match = re.search(r"\b(19|20)\d{2}\b", date_text)
            if y_match:
                year = int(y_match.group(0))

        # ── abstract snippet ──────────────────────────────────────────────────
        abstract: str | None = None
        abs_el = await item.query_selector(".app-card-open__description p")
        if abs_el:
            abstract = (await abs_el.inner_text()).strip() or None

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            journal=journal,
            abstract=abstract,
            url=article_url,
            source=self.name,
        )
