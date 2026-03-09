"""ScienceDirect browser-based search (no API key — uses a saved Playwright session).

Uses Firefox headless (preferred via _HEADLESS_PREFERENCE) which passes
Cloudflare Bot Management where Chromium headless is blocked.

Navigation strategy: go to /search, fill the form fields, submit, then
wait for li.ResultItem elements. Direct URL navigation to /search?qs=...
fails with a CSRF-related error; form submission does not.
"""
from __future__ import annotations
import asyncio
import re

from mosaic.models import Paper, SearchFilters
from mosaic.sources.base import BaseSource

_SD_BASE = "https://www.sciencedirect.com"


class ScienceDirectBrowserSource(BaseSource):
    """Search ScienceDirect via a saved Playwright browser session (no API key)."""

    name = "ScienceDirect"

    def available(self) -> bool:
        try:
            from mosaic.auth import find_session_for_url
            return find_session_for_url(_SD_BASE) is not None
        except Exception:
            return False

    def search(self, query: str, max_results: int = 25,
               filters: SearchFilters | None = None) -> list[Paper]:
        try:
            from mosaic.auth import find_session_for_url, _require_playwright
            _require_playwright()
            session_name = find_session_for_url(_SD_BASE)
            if not session_name:
                return []
            return asyncio.run(
                self._browser_search(query, max_results, session_name, filters)
            )
        except Exception:
            return []

    # ── async internals ───────────────────────────────────────────────────────

    async def _browser_search(self, query: str, max_results: int,
                               session_name: str,
                               filters: SearchFilters | None) -> list[Paper]:
        from mosaic.auth import session_path, _launch_browser
        from playwright.async_api import async_playwright

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
                # Navigate to the search form (direct URL construction triggers
                # a CSRF check; form submission avoids it)
                await page.goto(
                    f"{_SD_BASE}/search",
                    wait_until="networkidle",
                    timeout=30_000,
                )
                await self._fill_form(page, query, filters)
                await page.wait_for_load_state("networkidle", timeout=30_000)
                try:
                    await page.wait_for_selector("li.ResultItem", timeout=12_000)
                except Exception:
                    pass
                papers = await self._extract_results(page, max_results)
            except Exception:
                pass
            finally:
                await browser.close()
        return papers

    async def _fill_form(self, page, query: str,
                         filters: SearchFilters | None) -> None:
        """Fill the advanced search form fields and submit."""
        field = (filters.field or "all") if filters else "all"

        if field == "title":
            await page.fill("input[name=title]", query)
            submit_field = "input[name=title]"
        else:
            # "all" and "abstract" both use the main keyword textarea
            await page.fill("textarea[name=qs]", query)
            submit_field = "textarea[name=qs]"

        if filters:
            y_from = filters.year_from or (min(filters.years) if filters.years else None)
            y_to   = filters.year_to   or (max(filters.years) if filters.years else None)
            if y_from or y_to:
                date_str = f"{y_from or y_to}-{y_to or y_from}"
                await page.fill("input[name=date]", date_str)
            if filters.journal:
                await page.fill("input[name=pub]", filters.journal)

        await page.press(submit_field, "Enter")

    async def _extract_results(self, page, max_results: int) -> list[Paper]:
        items = await page.query_selector_all("li.ResultItem")
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
        # ── title + article URL ───────────────────────────────────────────────
        title_el = await item.query_selector("a.result-list-title-link")
        if not title_el:
            title_el = await item.query_selector("h2 a, h3 a")
        if not title_el:
            return None
        title = (await title_el.inner_text()).strip()
        if not title:
            return None

        href = await title_el.get_attribute("href") or ""
        article_url = f"{_SD_BASE}{href}" if href.startswith("/") else href or None

        # ── PII (used as dedup key when DOI is absent) ────────────────────────
        pii: str | None = None
        m = re.search(r"/pii/([A-Z0-9]+)", href)
        if m:
            pii = m.group(1)

        # ── authors ───────────────────────────────────────────────────────────
        authors: list[str] = []
        els = await item.query_selector_all("ol.Authors li span.author")
        if not els:
            els = await item.query_selector_all("ol.Authors li")
        for el in els:
            name = (await el.inner_text()).strip().rstrip(",").strip()
            if name:
                authors.append(name)

        # ── journal + year ────────────────────────────────────────────────────
        journal: str | None = None
        year: int | None = None
        pub_el = await item.query_selector(".srctitle-date-fields")
        if pub_el:
            pub_text = (await pub_el.inner_text()).strip()
            y_match = re.search(r"\b(19|20)\d{2}\b", pub_text)
            if y_match:
                year = int(y_match.group(0))
            # Journal name is in the link, before the date text
            j_el = await pub_el.query_selector("a.subtype-srctitle-link")
            if j_el:
                journal = (await j_el.inner_text()).strip() or None

        # ── open access + PDF link ────────────────────────────────────────────
        is_oa = bool(await item.query_selector("span.access-indicator-yes"))
        pdf_url: str | None = None
        pdf_el = await item.query_selector(
            "a.download-link[href*='/pdfft/'], a[href*='/pdfft/'], a[href*='/pdfdirect/']"
        )
        if pdf_el:
            pdf_href = await pdf_el.get_attribute("href") or ""
            pdf_url = f"{_SD_BASE}{pdf_href}" if pdf_href.startswith("/") else pdf_href

        return Paper(
            title=title,
            authors=authors,
            year=year,
            pii=pii,
            journal=journal,
            pdf_url=pdf_url,
            url=article_url,
            source=self.name,
            is_open_access=is_oa,
        )
