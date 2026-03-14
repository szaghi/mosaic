"""Shared parsing utilities for source implementations.

Centralises common patterns that were duplicated across 20+ source files:
year extraction, author normalisation, HTML stripping, and safe accessors.
"""

from __future__ import annotations

import re


def parse_year(value: str | int | None) -> int | None:
    """Safely extract a four-digit year from a string, int, or None.

    Handles bare years (``"2020"``), date-prefixed strings (``"2020-03-15"``),
    and integer values.  Returns ``None`` when no valid year can be extracted.

    >>> parse_year("2020-03-15")
    2020
    >>> parse_year(2021)
    2021
    >>> parse_year("")
    >>> parse_year(None)
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Try direct conversion for pure integers
    if s.isdigit() and len(s) == 4:
        return int(s)
    # Regex fallback: grab the first four-digit group
    m = re.search(r"\b(\d{4})\b", s)
    return int(m.group(1)) if m else None


def parse_year_earliest(item: dict, fields: list[str]) -> int | None:
    """Parse year from multiple date fields, preferring the earliest.

    Useful for sources like PubMed/PMC that have multiple date fields
    (``epubdate``, ``pubdate``) where the earliest is most relevant.

    >>> parse_year_earliest({"epubdate": "2020", "pubdate": "2021"}, ["epubdate", "pubdate"])
    2020
    """
    best: int | None = None
    for field in fields:
        raw = str(item.get(field) or "")
        if raw:
            part = raw.split()[0]
            y = parse_year(part)
            if y is not None and (best is None or y < best):
                best = y
    return best


def extract_first(value: str | list | None) -> str | None:
    """Return the first element if *value* is a list, the value itself if a
    string, or ``None``.

    Many APIs return a field that is sometimes a string, sometimes a list
    (e.g. BASE ``dctitle``, Crossref ``title``, NASA ADS ``title``).

    >>> extract_first(["hello", "world"])
    'hello'
    >>> extract_first("hello")
    'hello'
    >>> extract_first([])
    >>> extract_first(None)
    """
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value


def strip_html(text: str | None) -> str | None:
    """Remove HTML/XML tags and collapse whitespace.

    Returns ``None`` when the result is empty or the input is ``None``.

    >>> strip_html("<jats:p>Hello <b>world</b></jats:p>")
    'Hello world'
    >>> strip_html("")
    >>> strip_html(None)
    """
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text).strip()
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or None


def normalise_doi(doi_raw: str | None) -> str | None:
    """Strip common URL prefixes from a DOI string.

    >>> normalise_doi("https://doi.org/10.1234/foo")
    '10.1234/foo'
    >>> normalise_doi("10.1234/foo")
    '10.1234/foo'
    >>> normalise_doi("")
    >>> normalise_doi(None)
    """
    if not doi_raw:
        return None
    cleaned = doi_raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/"):
        cleaned = cleaned.removeprefix(prefix)
    return cleaned or None


def parse_authors_name_key(items: list[dict], key: str = "name") -> list[str]:
    """Extract author names from a list of dicts using a single key.

    Used by: Semantic Scholar, PubMed, PMC, CORE, Zenodo, DOAJ.

    >>> parse_authors_name_key([{"name": "Alice"}, {"name": "Bob"}])
    ['Alice', 'Bob']
    """
    return [a.get(key, "") for a in items if a.get(key)]


def parse_authors_given_family(items: list[dict]) -> list[str]:
    """Parse authors from Crossref-style ``{given, family}`` dicts.

    Produces ``"Family, Given"`` format for consistency.

    >>> parse_authors_given_family([{"family": "Smith", "given": "John"}])
    ['Smith, John']
    """
    authors: list[str] = []
    for a in items:
        family = a.get("family", "")
        given = a.get("given", "")
        if family and given:
            authors.append(f"{family}, {given}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)
    return authors


def split_authors(text: str, sep: str = ",") -> list[str]:
    """Split an author string by a separator and strip whitespace.

    >>> split_authors("Smith, J, Doe, K", sep=",")
    ['Smith', 'J', 'Doe', 'K']
    >>> split_authors("Smith; Doe", sep=";")
    ['Smith', 'Doe']
    """
    if not text:
        return []
    return [a.strip() for a in text.split(sep) if a.strip()]
