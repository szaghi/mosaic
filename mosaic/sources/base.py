"""Abstract base class for all search sources and shared helpers."""

from __future__ import annotations

import email.utils
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable

import httpx

from mosaic.models import Paper, SearchFilters

log = logging.getLogger(__name__)


class BaseSource(ABC):
    name: str = ""

    @abstractmethod
    def search(
        self, query: str, max_results: int = 25, filters: SearchFilters | None = None
    ) -> list[Paper]:
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


# ---------------------------------------------------------------------------
# Shared helpers for source implementations
# ---------------------------------------------------------------------------


def extract_year_range(filters: SearchFilters | None) -> tuple[int | None, int | None]:
    """Extract ``(year_from, year_to)`` from filters, coalescing an explicit years list.

    Returns:
        A tuple ``(year_from, year_to)`` where either or both may be ``None``.
    """
    if filters is None:
        return None, None
    y_from = filters.year_from or (min(filters.years) if filters.years else None)
    y_to = filters.year_to or (max(filters.years) if filters.years else None)
    return y_from, y_to


def build_field_query(
    query: str,
    filters: SearchFilters | None,
    title_prefix: str,
    abstract_prefix: str,
    default_prefix: str = "",
    phrase: bool = False,
) -> str:
    """Build a field-scoped query string from filters.

    If ``filters.raw_query`` is set it is returned verbatim.  Otherwise the
    query is prefixed according to ``filters.field``.

    Args:
        query: The original user query.
        filters: Optional filters (may be ``None``).
        title_prefix: Format string applied for title scoping (e.g. ``'ti:{}'``).
            Use ``{}`` as placeholder for *query*.
        abstract_prefix: Format string for abstract scoping (e.g. ``'abs:{}'``).
        default_prefix: Format string used when no field scoping is active.
            Defaults to bare *query* (``""``).
        phrase: When True, a multi-word *query* is quoted (see
            ``phrase_if_needed``) before title/abstract scoping, for query
            languages where an unquoted ``ti:a b`` only scopes the first word.

    Returns:
        The scoped query string.
    """
    if filters and filters.raw_query:
        return filters.raw_query
    scoped = phrase_if_needed(query) if phrase else query
    if filters and filters.field == "title":
        return title_prefix.format(scoped)
    if filters and filters.field == "abstract":
        return abstract_prefix.format(scoped)
    if default_prefix:
        return default_prefix.format(query)
    return query


def lucene_phrase(value: str) -> str:
    """Return *value* as a double-quoted Lucene phrase with inner quotes escaped.

    >>> print(lucene_phrase('say "hi"'))
    "say \\"hi\\""
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def phrase_if_needed(value: str) -> str:
    """Quote a multi-word *value* so a field prefix scopes all of its words.

    Values that already contain quotes, parentheses or boolean operators are
    returned unchanged — they are treated as deliberate query syntax.

    >>> phrase_if_needed("deep learning")
    '"deep learning"'
    >>> phrase_if_needed("transformer")
    'transformer'
    >>> phrase_if_needed('"exact phrase" AND x')
    '"exact phrase" AND x'
    """
    stripped = value.strip()
    if not any(c.isspace() for c in stripped):
        return stripped
    if any(c in stripped for c in '"()') or any(
        f" {op} " in f" {stripped} " for op in ("AND", "OR", "NOT")
    ):
        return stripped
    return lucene_phrase(stripped)


def any_of(values: Iterable[str], template: str) -> str:
    """Render *values* through *template* and OR them together.

    Used for repeatable filters (``-a A -a B``) whose documented semantics are
    "match at least one".  A single value is returned without parentheses.

    >>> any_of(["A", "B"], 'au:"{}"')
    '(au:"A" OR au:"B")'
    >>> any_of(["A"], 'au:"{}"')
    'au:"A"'
    """
    parts = [template.format(v) for v in values if v]
    if len(parts) == 1:
        return parts[0]
    return f"({' OR '.join(parts)})" if parts else ""


def build_scopus_query(query: str, filters: SearchFilters | None) -> str:
    """Build a Scopus boolean query string from *query* and *filters*.

    Shared by both ``ScopusAPISource`` and ``ScopusBrowserSource`` to prevent
    drift between the two implementations.  The user query is not wrapped in
    quotes: ``TITLE-ABS-KEY(a b c)`` matches all terms (like every other
    source), whereas a quoted value would be a loose phrase and would break
    queries that already contain quotes.

    Returns:
        A Scopus advanced-search query string.
    """
    if filters and filters.raw_query:
        scopus_query = filters.raw_query
    elif filters and filters.field == "title":
        scopus_query = f"TITLE({query})"
    elif filters and filters.field == "abstract":
        scopus_query = f"ABS({query})"
    else:
        scopus_query = f"TITLE-ABS-KEY({query})"

    if filters:
        y_from, y_to = extract_year_range(filters)
        if y_from:
            scopus_query += f" AND PUBYEAR > {y_from - 1}"
        if y_to:
            scopus_query += f" AND PUBYEAR < {y_to + 1}"
        if filters.authors:
            # Scopus has no quote escaping — drop embedded quotes instead.
            authors = [a.replace('"', "") for a in filters.authors]
            scopus_query += " AND " + any_of(authors, 'AUTH("{}")')
        if filters.journal:
            journal = filters.journal.replace('"', "")
            scopus_query += f' AND SRCTITLE("{journal}")'
    return scopus_query


def ensure_playwright() -> None:
    """Raise ``SourceError`` when Playwright is not importable.

    Browser sources call this instead of ``mosaic.auth._require_playwright``,
    which prints to the terminal and raises ``SystemExit`` — neither is
    acceptable inside a search worker (``SystemExit`` escapes
    ``except Exception`` and would kill a web UI job).
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        from mosaic.errors import SourceError

        raise SourceError(
            "Playwright is not installed — pip install 'mosaic-search[browser]'"
        ) from None


# ---------------------------------------------------------------------------
# Rate limiting and retries
# ---------------------------------------------------------------------------

_RETRY_STATUSES = frozenset({429, 503})
_MAX_RETRIES = 2
_MAX_RETRY_WAIT = 10.0


class Throttle:
    """Process-wide minimum interval between requests (thread-safe).

    Instances are meant to live at module level so the interval survives
    ``build_sources()`` rebuilding source objects for every search.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self, min_interval: float) -> None:
        """Block until at least *min_interval* seconds have passed since the last call."""
        if min_interval <= 0:
            return
        with self._lock:
            delay = self._last + min_interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


def _retry_after_seconds(resp: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retrying *resp* (``Retry-After`` or exponential backoff)."""
    fallback = 2.0**attempt
    try:
        raw = resp.headers.get("Retry-After")
    except Exception:
        raw = None
    if not isinstance(raw, str) or not raw.strip():
        return fallback
    raw = raw.strip()
    try:
        seconds = float(raw)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return fallback
        seconds = when.timestamp() - time.time()
    return max(0.0, min(seconds, _MAX_RETRY_WAIT))


def with_retry(send: Callable[[], httpx.Response], retries: int = _MAX_RETRIES) -> httpx.Response:
    """Call *send* and retry (bounded) while the server answers 429 or 503.

    *send* is a zero-argument callable performing the request, e.g.
    ``lambda: client.get(url, params=params)``.  The last response is
    returned unchanged, so callers keep using ``raise_for_status()``.
    """
    for attempt in range(retries + 1):
        resp = send()
        if resp.status_code not in _RETRY_STATUSES or attempt == retries:
            return resp
        wait = _retry_after_seconds(resp, attempt)
        log.debug("HTTP %s — retrying in %.1fs", resp.status_code, wait)
        time.sleep(wait)
    return resp  # pragma: no cover — loop always returns
