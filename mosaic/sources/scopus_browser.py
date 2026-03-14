"""Scopus browser-based search (no API key — uses a saved Playwright session).

Uses headless Firefox with a saved Elsevier SSO session. Because Scopus and
ScienceDirect share the same ``id.elsevier.com`` SSO, a single browser login
covers both sites. To save a session::

    mosaic auth login scopus --url https://www.scopus.com

Then complete the full institutional SSO flow until the Scopus homepage shows
your name, and press Enter in the terminal.

.. note::
    Scopus uses a heavily JavaScript-rendered interface. The CSS selectors in
    this module target Scopus's advanced-search form and result-list layout as
    of early 2026 — they may need adjustment if Scopus updates its frontend.
    Open an issue at https://github.com/szaghi/mosaic if search returns empty
    results after a known-working login.
"""

from __future__ import annotations

import asyncio
import re

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource, build_scopus_query

_SCOPUS_BASE = "https://www.scopus.com"
_SEARCH_URL = f"{_SCOPUS_BASE}/search/form.uri#advanced"


class ScopusBrowserSource(BaseSource):
    """Search Scopus via a saved Playwright browser session (no API key)."""

    name = "Scopus"

    def available(self) -> bool:
        """Return True when a valid saved Playwright session exists for Scopus.

        Returns:
            True if a session file is found and has not expired; False
            otherwise or if the ``mosaic.auth`` module is unavailable.
        """
        try:
            from mosaic.auth import find_session_for_url, has_browser, session_is_valid

            if not has_browser():
                return False
            session_name = find_session_for_url(_SCOPUS_BASE)
            return session_name is not None and session_is_valid(session_name)
        except Exception:
            return False

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        """Search Scopus using a headless browser with a saved session.

        Loads the saved Playwright session and runs an async browser search
        via the Scopus advanced-search form. Returns an empty list on any
        error (missing session, expired login, or unexpected page structure).

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to collect from the page.
            filters: Optional filters for field scoping and year range.
                Author and journal filters are translated into Scopus boolean
                query syntax appended to the search string.

        Returns:
            A list of Paper objects scraped from the results page, or an
            empty list if the session is invalid or the search fails.
        """
        try:
            from mosaic.auth import _require_playwright, find_session_for_url

            _require_playwright()
            session_name = find_session_for_url(_SCOPUS_BASE)
            if not session_name:
                return []
            return asyncio.run(self._browser_search(query, max_results, session_name, filters))
        except Exception:
            return []

    # ── async internals ───────────────────────────────────────────────────────

    async def _browser_search(
        self,
        query: str,
        max_results: int,
        session_name: str,
        filters: SearchFilters | None,
    ) -> list[Paper]:
        """Async implementation of the Scopus browser search.

        Navigates to the Scopus advanced-search form, fills the query
        textarea, submits, and extracts result rows. Detects SSO redirects
        that indicate an expired session and prints a helpful message.

        Args:
            query: Free-text search query.
            max_results: Maximum number of result rows to parse.
            session_name: Name of the saved Playwright session to load.
            filters: Optional filters forwarded to ``_build_query``.

        Returns:
            A list of Paper objects extracted from the results page.
        """
        from playwright.async_api import async_playwright

        from mosaic.auth import _launch_browser, session_path

        state_file = session_path(session_name)

        papers: list[Paper] = []
        async with async_playwright() as p:
            browser = await _launch_browser(p, headless=True)
            context = await browser.new_context(storage_state=str(state_file))
            page = await context.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            try:
                from rich import print as rprint

                await page.goto(
                    _SEARCH_URL,
                    wait_until="networkidle",
                    timeout=30_000,
                )
                if "id.elsevier.com" in page.url:
                    rprint(
                        "[yellow]Scopus session has expired.[/yellow] "
                        "Run: [bold]mosaic auth login scopus "
                        "--url https://www.scopus.com[/bold]"
                    )
                    return []

                await self._fill_form(page, query, filters)
                await page.wait_for_load_state("networkidle", timeout=30_000)

                if "id.elsevier.com" in page.url:
                    rprint(
                        "[yellow]Scopus session has expired.[/yellow] "
                        "Run: [bold]mosaic auth login scopus "
                        "--url https://www.scopus.com[/bold]"
                    )
                    return []

                try:
                    await page.wait_for_selector(
                        "[data-e2e='search-result-row'], tr.resultRow, [data-testid='result-row']",
                        timeout=15_000,
                    )
                except Exception:
                    pass

                papers = await self._extract_results(page, max_results)
                if not papers:
                    rprint("[dim]Scopus (browser): no results for this query.[/dim]")
            except Exception:
                pass
            finally:
                await browser.close()
        return papers

    @staticmethod
    def _build_query(query: str, filters: SearchFilters | None) -> str:
        """Translate query and filters into Scopus boolean query syntax."""
        return build_scopus_query(query, filters)

    async def _fill_form(self, page, query: str, filters: SearchFilters | None) -> None:
        """Fill the Scopus advanced-search textarea and submit.

        Tries multiple known textarea selectors in order. Submits via Enter
        key press after filling.

        Args:
            page: A Playwright ``Page`` object with the advanced-search form
                loaded.
            query: Free-text search query.
            filters: Optional filters forwarded to ``_build_query``.
        """
        scopus_query = self._build_query(query, filters)

        filled = False
        for sel in ("textarea[name='searchfield']", "#queryField", "textarea"):
            try:
                await page.fill(sel, scopus_query)
                filled = True
                break
            except Exception:
                continue

        if filled:
            await page.keyboard.press("Enter")

    async def _extract_results(self, page, max_results: int) -> list[Paper]:
        """Extract up to ``max_results`` Paper objects from the loaded results page.

        Tries multiple known result-row selectors in order.

        Args:
            page: A Playwright ``Page`` object with results already loaded.
            max_results: Maximum number of result rows to parse.

        Returns:
            A list of Paper objects; items that fail to parse are silently skipped.
        """
        items = []
        for sel in (
            "[data-e2e='search-result-row']",
            "tr.resultRow",
            "[data-testid='result-row']",
            ".resultItem",
        ):
            items = await page.query_selector_all(sel)
            if items:
                break

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
        """Parse a single result-row Playwright element into a Paper.

        Tries multiple known CSS selectors for title, authors, and source
        metadata to handle different versions of the Scopus frontend.

        Args:
            item: A Playwright ``ElementHandle`` for a result-row node.

        Returns:
            A Paper if a non-empty title can be found, otherwise ``None``.
        """
        # ── title + article URL ───────────────────────────────────────────────
        title_el = None
        for sel in (
            "a[data-e2e='result-title']",
            "a.docTitle",
            "a[data-testid='result-title']",
            "h3 a",
            "td.title a",
        ):
            title_el = await item.query_selector(sel)
            if title_el:
                break

        if not title_el:
            return None
        title = (await title_el.inner_text()).strip()
        if not title:
            return None

        href = await title_el.get_attribute("href") or ""
        article_url = f"{_SCOPUS_BASE}{href}" if href.startswith("/") else href or None

        # ── DOI from URL or explicit element ─────────────────────────────────
        doi: str | None = None
        doi_m = re.search(r"10\.\d{4,}/[^\s&?#]+", href)
        if doi_m:
            doi = doi_m.group(0)
        if not doi:
            doi_el = await item.query_selector("[data-e2e='result-doi'], .doi")
            if doi_el:
                raw = (await doi_el.inner_text()).strip()
                doi_m2 = re.search(r"10\.\d{4,}/\S+", raw)
                if doi_m2:
                    doi = doi_m2.group(0).rstrip(".,")

        # ── authors ───────────────────────────────────────────────────────────
        authors: list[str] = []
        for sel in ("[data-e2e='result-authors'] a", ".authorSection a", ".authorsLink a"):
            els = await item.query_selector_all(sel)
            if els:
                for el in els:
                    name = (await el.inner_text()).strip().rstrip(",").strip()
                    if name:
                        authors.append(name)
                break
        if not authors:
            for sel in ("[data-e2e='result-authors']", ".authors"):
                auth_el = await item.query_selector(sel)
                if auth_el:
                    raw_authors = (await auth_el.inner_text()).strip()
                    authors = [a.strip() for a in raw_authors.split(",") if a.strip()]
                    break

        # ── journal + year ────────────────────────────────────────────────────
        journal: str | None = None
        year: int | None = None
        for sel in (
            "[data-e2e='result-source']",
            ".sourceTitle",
            "td.srctitle",
        ):
            meta_el = await item.query_selector(sel)
            if meta_el:
                meta_text = (await meta_el.inner_text()).strip()
                y_m = re.search(r"\b(19|20)\d{2}\b", meta_text)
                if y_m:
                    year = int(y_m.group(0))
                journal = re.sub(r",?\s*(19|20)\d{2}.*$", "", meta_text).strip() or None
                break

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            journal=journal,
            url=article_url,
            source=self.name,
            is_open_access=False,
        )
