"""PDF text extraction via pymupdf (optional dependency)."""

from __future__ import annotations

import re
from pathlib import Path

# Pages read per PDF; guards indexing against book-sized or pathological files.
MAX_PAGES = 500


def _import_pymupdf():
    """Import pymupdf under its current name; ``fitz`` is the deprecated alias
    (importing it prints a deprecation warning on recent releases)."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # pymupdf < 1.24.3
    return pymupdf


def is_available() -> bool:
    """Return True if pymupdf is importable."""
    try:
        _import_pymupdf()
        return True
    except ImportError:
        return False


def extract_text(path: str | Path, *, max_pages: int = MAX_PAGES) -> str:
    """Extract plain text from the first *max_pages* pages of a PDF using pymupdf.

    Returns an empty string on any failure (encrypted, corrupted, image-only).
    Never raises -- extraction failures must not block indexing.  The
    document is always closed.
    """
    try:
        pymupdf = _import_pymupdf()
    except ImportError as e:
        raise ImportError(
            "pymupdf is required for full-text PDF indexing. Run: pipx inject mosaic-search pymupdf"
        ) from e

    try:
        doc = pymupdf.open(str(path))
    except Exception:
        return ""
    try:
        if doc.is_encrypted:
            return ""
        parts = []
        for page_no, page in enumerate(doc):
            if page_no >= max_pages:
                break
            parts.append(page.get_text())
        text = "\n".join(parts)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        return ""
    finally:
        try:
            doc.close()
        except Exception:
            pass
