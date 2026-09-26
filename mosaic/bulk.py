"""Utilities for extracting DOIs from BibTeX and CSV files."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from mosaic.parsing import normalise_doi

# A bare DOI: "10." + registrant code (digits, may have sub-codes) + "/" + suffix
_DOI_RE = re.compile(r"10\.\d+(?:\.\d+)*/\S+")


def read_dois(path: Path) -> list[str]:
    """Return a deduplicated list of DOIs from a .bib or .csv file.

    DOIs are returned in bare form (``10.xxx/yyy``) whatever the input looked
    like (``https://doi.org/…``, ``doi:…``); duplicates are detected
    case-insensitively, as DOIs are case-insensitive.
    """
    suffix = path.suffix.lower()
    if suffix == ".bib":
        return _read_bib(path)
    if suffix == ".csv":
        return _read_csv(path)
    raise ValueError(f"Unsupported file type '{suffix}'. Use .bib or .csv.")


def _clean_doi(raw: str) -> str | None:
    """Reduce *raw* (bare DOI, DOI URL, ``doi:`` prefix …) to a bare DOI, or None."""
    cleaned = normalise_doi(raw)
    if not cleaned:
        return None
    m = _DOI_RE.search(cleaned)
    if not m:
        return None
    return m.group(0).rstrip(".,;")


def _dedupe(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    dois: list[str] = []
    for raw in candidates:
        doi = _clean_doi(raw)
        if doi and doi.lower() not in seen:
            dois.append(doi)
            seen.add(doi.lower())
    return dois


def _read_bib(path: Path) -> list[str]:
    """Extract DOIs from a BibTeX file using regex (no extra dependency)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Match:  doi = {10.xxx/yyy}  or  doi = "https://doi.org/10.xxx/yyy"  (case-insensitive key)
    pattern = re.compile(r'\bdoi\s*=\s*[{"]\s*([^"}{\s,]+)', re.IGNORECASE)
    return _dedupe([m.group(1).rstrip(",; \t}") for m in pattern.finditer(text)])


def _read_csv(path: Path) -> list[str]:
    """Extract DOIs from a CSV file that has a 'doi' (case-insensitive) column."""
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        doi_col = next((h for h in headers if h.strip().lower() == "doi"), None)
        if doi_col is None:
            raise ValueError("CSV has no 'doi' column.")
        return _dedupe([(row.get(doi_col) or "").strip() for row in reader])
