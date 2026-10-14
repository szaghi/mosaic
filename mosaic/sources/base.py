"""Abstract base class for all search sources and shared helpers."""

from __future__ import annotations

import datetime
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any

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

    Returns:
        The scoped query string.
    """
    if filters and filters.raw_query:
        return filters.raw_query
    if filters and filters.field == "title":
        return title_prefix.format(query)
    if filters and filters.field == "abstract":
        return abstract_prefix.format(query)
    if default_prefix:
        return default_prefix.format(query)
    return query


def build_scopus_query(query: str, filters: SearchFilters | None) -> str:
    """Build a Scopus boolean query string from *query* and *filters*.

    Shared by both ``ScopusAPISource`` and ``ScopusBrowserSource`` to prevent
    drift between the two implementations.

    Returns:
        A Scopus advanced-search query string.
    """
    if filters and filters.raw_query:
        scopus_query = filters.raw_query
    elif filters and filters.field == "title":
        scopus_query = f'TITLE("{query}")'
    elif filters and filters.field == "abstract":
        scopus_query = f'ABS("{query}")'
    else:
        scopus_query = f'TITLE-ABS-KEY("{query}")'

    if filters:
        y_from, y_to = extract_year_range(filters)
        if y_from:
            scopus_query += f" AND PUBYEAR > {y_from - 1}"
        if y_to:
            scopus_query += f" AND PUBYEAR < {y_to + 1}"
        if filters.authors:
            for author in filters.authors:
                scopus_query += f' AND AUTH("{author}")'
        if filters.journal:
            scopus_query += f' AND SRCTITLE("{filters.journal}")'
    return scopus_query


# ---------------------------------------------------------------------------
# HTTP: rate-limit retry and readable error messages (issue #16)
# ---------------------------------------------------------------------------

# Statuses that mean "slow down", not "you are wrong": retried when the wait is short.
_RETRY_STATUSES = frozenset({429, 503})
# Phrases quota-limited APIs put in 401/403 bodies (IEEE "Developer Over Rate",
# Springer/Elsevier "quota exceeded", ...).
_QUOTA_MARKERS = ("quota", "over rate", "rate limit", "limit exceeded", "too many requests")


def retry_after_seconds(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date) into seconds.

    Returns None when the header is absent or unparseable.
    """
    if not value:
        return None
    value = value.strip()
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.UTC)
    return max((when - datetime.datetime.now(datetime.UTC)).total_seconds(), 0.0)


class RetryTransport(httpx.BaseTransport):
    """Transport that retries 429/503 responses when the server asks for a short wait.

    The wait is the server's ``Retry-After`` when present, else exponential
    backoff (1 s, 2 s, ...). A requested wait longer than *max_wait* is not
    honoured: the response is returned as-is so the source fails fast and the
    caller reports it, instead of a search hanging for minutes.

    Parameters
    ----------
    max_retries : int
        Retries after the first attempt.
    max_wait : float
        Longest single wait, in seconds, that will be honoured.
    transport : httpx.BaseTransport or None
        Wrapped transport; defaults to ``httpx.HTTPTransport()``.
    sleep : callable
        Injected for tests.
    """

    def __init__(
        self,
        max_retries: int = 2,
        max_wait: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._inner = transport or httpx.HTTPTransport()
        self._max_retries = max_retries
        self._max_wait = max_wait
        self._sleep = sleep

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            response = self._inner.handle_request(request)
            if response.status_code not in _RETRY_STATUSES or attempt == self._max_retries:
                return response
            wait = retry_after_seconds(response.headers.get("retry-after"))
            if wait is None:
                wait = float(2**attempt)
            if wait > self._max_wait:
                return response
            response.close()
            log.info(
                "HTTP %s from %s; retrying in %.1fs (%d/%d)",
                response.status_code,
                request.url.host,
                wait,
                attempt + 1,
                self._max_retries,
            )
            self._sleep(wait)
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        self._inner.close()


def http_client(**kwargs: Any) -> httpx.Client:
    """Return an ``httpx.Client`` whose requests retry short rate-limit waits.

    Drop-in for ``httpx.Client(...)`` in sources. httpx mounts proxies from
    ``HTTP(S)_PROXY`` env vars as separate transports, so proxied requests
    still work but skip the retry layer.
    """
    kwargs.setdefault("transport", RetryTransport())
    return httpx.Client(**kwargs)


def describe_http_error(exc: BaseException) -> str:
    """Turn a source failure into a one-line, user-actionable message."""
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        code = resp.status_code
        if code == 429:
            wait = retry_after_seconds(resp.headers.get("retry-after"))
            hint = f"; retry in ~{wait:.0f}s" if wait is not None else "; try again later"
            return f"rate limited (HTTP 429){hint}"
        if code in (401, 403):
            try:
                body = resp.text[:1000].lower()
            except Exception:
                body = ""
            if any(m in body for m in _QUOTA_MARKERS):
                return f"API quota exhausted (HTTP {code}); try again later or tomorrow"
            return f"access denied (HTTP {code}); check the API key / credentials"
        return f"HTTP {code} from {resp.request.url.host}"
    if isinstance(exc, httpx.TimeoutException):
        return "timed out"
    return str(exc)
