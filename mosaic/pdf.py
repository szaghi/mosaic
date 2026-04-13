"""PDF text extraction via pymupdf (optional dependency)."""

from __future__ import annotations

from pathlib import Path


def is_available() -> bool:
    """Return True if pymupdf (fitz) is importable."""
    try:
        import fitz  # noqa: F401

        return True
    except ImportError:
        return False


def extract_text(path: str | Path) -> str:
    """Extract plain text from a PDF file using pymupdf.

    Returns an empty string on any failure (encrypted, corrupted, image-only).
    Never raises -- extraction failures must not block indexing.
    """
    try:
        import fitz
    except ImportError as e:
        raise ImportError(
            "pymupdf is required for full-text PDF indexing. Run: pipx inject mosaic-search pymupdf"
        ) from e

    try:
        doc = fitz.open(str(path))
        if doc.is_encrypted:
            return ""
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        text = "\n".join(parts)
        # Collapse excessive blank lines
        import re

        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        return ""
