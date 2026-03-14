"""Utilities for extracting DOIs from BibTeX and CSV files."""

from __future__ import annotations

import csv
import re
from pathlib import Path


def read_dois(path: Path) -> list[str]:
    """Return a deduplicated list of DOIs from a .bib or .csv file."""
    suffix = path.suffix.lower()
    if suffix == ".bib":
        return _read_bib(path)
    if suffix == ".csv":
        return _read_csv(path)
    raise ValueError(f"Unsupported file type '{suffix}'. Use .bib or .csv.")


def _read_bib(path: Path) -> list[str]:
    """Extract DOIs from a BibTeX file using regex (no extra dependency)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Match:  doi = {10.xxx/yyy}  or  doi = "10.xxx/yyy"  (case-insensitive key)
    pattern = re.compile(r'\bdoi\s*=\s*[{"]\s*(10\.[^\s"}{,]+)', re.IGNORECASE)
    seen: set[str] = set()
    dois: list[str] = []
    for m in pattern.finditer(text):
        doi = m.group(1).rstrip(",; \t}")
        if doi and doi not in seen:
            dois.append(doi)
            seen.add(doi)
    return dois


def _read_csv(path: Path) -> list[str]:
    """Extract DOIs from a CSV file that has a 'doi' (case-insensitive) column."""
    seen: set[str] = set()
    dois: list[str] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        doi_col = next((h for h in headers if h.strip().lower() == "doi"), None)
        if doi_col is None:
            raise ValueError("CSV has no 'doi' column.")
        for row in reader:
            val = (row.get(doi_col) or "").strip()
            if val and val not in seen:
                dois.append(val)
                seen.add(val)
    return dois
