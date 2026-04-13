"""Citation formatting: BibTeX (local) and human-readable styles via Crossref content negotiation."""

from __future__ import annotations

import logging
import subprocess
import sys

import httpx

from mosaic.exporter import _bibtex_entry
from mosaic.models import Paper
from mosaic.parsing import (
    extract_first,
    parse_authors_given_family,
    parse_year,
    strip_html,
)

_log = logging.getLogger(__name__)

_CR_WORKS = "https://api.crossref.org/works"
_DOI_BASE = "https://doi.org"

SUPPORTED_STYLES: list[str] = ["bibtex", "apa", "mla", "chicago", "harvard", "vancouver"]


# ---------------------------------------------------------------------------
# Metadata resolution
# ---------------------------------------------------------------------------


def _parse_crossref_item(item: dict) -> Paper:
    """Parse a Crossref works item dict into a Paper.

    Args:
        item: A dict from the Crossref works endpoint message body.

    Returns:
        A Paper populated from the Crossref fields.
    """
    title = extract_first(item.get("title")) or ""
    authors = parse_authors_given_family(item.get("author") or [])

    year: int | None = None
    date_parts = item.get("published", {}).get("date-parts", [])
    if date_parts and date_parts[0]:
        year = parse_year(date_parts[0][0])

    doi = item.get("DOI") or None
    abstract = strip_html(item.get("abstract"))
    journal = extract_first(item.get("container-title"))
    url = item.get("URL") or None
    volume = item.get("volume") or None
    issue = item.get("issue") or None
    pages = item.get("page") or None

    pdf_url: str | None = None
    for link in item.get("link") or []:
        if link.get("content-type") == "application/pdf":
            pdf_url = link.get("URL") or None
            break

    return Paper(
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        abstract=abstract,
        journal=journal,
        volume=volume,
        issue=issue,
        pages=pages,
        url=url,
        pdf_url=pdf_url,
        source="Crossref",
        is_open_access=pdf_url is not None,
    )


def fetch_paper_by_doi(doi: str, email: str = "") -> Paper:
    """Fetch paper metadata from the Crossref works endpoint by DOI.

    Args:
        doi: Bare DOI string (no URL prefix).
        email: Optional email for Crossref polite pool (higher rate limits).

    Returns:
        A Paper populated from the Crossref response.

    Raises:
        httpx.HTTPStatusError: On 404 (DOI not found) or other HTTP errors.
        httpx.ConnectError: When the network is unavailable.
        httpx.TimeoutException: When the request exceeds 30 seconds.
    """
    params: dict[str, str] = {}
    if email:
        params["mailto"] = email

    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{_CR_WORKS}/{doi}", params=params)
        resp.raise_for_status()
        item = resp.json().get("message", {})

    return _parse_crossref_item(item)


def resolve_paper(doi: str, cache: object, email: str = "") -> Paper:
    """Resolve a DOI to a Paper, checking the local cache first.

    On a cache miss, fetches from Crossref and saves the result to cache.

    Args:
        doi: Raw DOI string (URL prefix is stripped automatically by the caller).
        cache: A Cache instance for local lookup and persistence.
        email: Optional email for the Crossref polite pool.

    Returns:
        A Paper object for the given DOI.

    Raises:
        httpx.HTTPStatusError: When the DOI is not found (404) or another HTTP error occurs.
        httpx.ConnectError: When the network is unavailable.
        httpx.TimeoutException: When the Crossref request times out.
    """
    stub = Paper(title=doi, doi=doi, source="manual")
    cached = cache.get_by_uid(stub.uid)  # type: ignore[union-attr]
    if cached is not None:
        _log.debug("DOI %s found in local cache", doi)
        return cached

    _log.debug("DOI %s not in cache; fetching from Crossref", doi)
    paper = fetch_paper_by_doi(doi, email)
    cache.save(paper)  # type: ignore[union-attr]
    return paper


# ---------------------------------------------------------------------------
# Citation formatting
# ---------------------------------------------------------------------------


def bibtex_citation(paper: Paper) -> str:
    """Return a formatted BibTeX entry for a single paper.

    Args:
        paper: The Paper to format.

    Returns:
        A complete BibTeX entry string ready for stdout.
    """
    return _bibtex_entry(paper, 1)


def fetch_formatted_citation(doi: str, style: str, email: str = "") -> str:
    """Fetch a pre-formatted citation string from Crossref content negotiation.

    Uses the doi.org endpoint with an Accept header of the form
    text/x-bibliography; style=<style>; locale=en-US.

    Args:
        doi: Bare DOI string (no URL prefix).
        style: A valid CSL style name (e.g. apa, mla, chicago-author-date).
        email: Optional email included in the User-Agent for Crossref polite pool.

    Returns:
        The formatted citation string as returned by doi.org.

    Raises:
        httpx.HTTPStatusError: On 404 (DOI not found) or other HTTP errors.
        httpx.ConnectError: When the network is unavailable.
        httpx.TimeoutException: When the request exceeds 30 seconds.
        ValueError: When the response Content-Type is not text/bibliography.
    """
    accept = f"text/x-bibliography; style={style}; locale=en-US"
    headers: dict[str, str] = {"Accept": accept}
    if email:
        headers["User-Agent"] = f"mosaic/1.0 (mailto:{email})"

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(f"{_DOI_BASE}/{doi}", headers=headers)
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "bibliography" not in content_type and not resp.text.strip():
        raise ValueError(
            f"Unexpected response Content-Type '{content_type}' for style '{style}'. "
            "The DOI may not support this citation style."
        )

    return resp.text.strip()


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


def copy_to_clipboard(text: str) -> bool:
    """Attempt to copy text to the system clipboard.

    Tries pyperclip first, then platform-native subprocess tools.
    Never raises — returns False and logs a warning on failure.

    Args:
        text: The citation text to place on the clipboard.

    Returns:
        True if the copy succeeded, False otherwise.
    """
    # 1. pyperclip (cross-platform, optional dependency)
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        pass

    # 2. Platform-native subprocess fallbacks
    if sys.platform == "darwin":
        candidates: list[list[str]] = [["pbcopy"]]
    elif sys.platform == "win32":
        candidates = [["clip"]]
    else:
        candidates = [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]

    for cmd in candidates:
        try:
            subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
            return True
        except Exception:
            continue

    _log.warning("copy_to_clipboard: all methods failed; text not copied")
    return False
