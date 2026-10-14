"""File PDFs the user already has into the library (``mosaic import``).

For PDFs downloaded by hand, e.g. a ``--handoff`` download that finished
after MOSAIC had moved on. The paper's DOI is taken from ``--doi`` or detected
from the file; metadata comes from the cache or Crossref, and the PDF is moved
into the download directory under the usual name and recorded in the cache.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from mosaic.cite import paper_for_download
from mosaic.db import Cache
from mosaic.errors import MosaicError
from mosaic.handoff import _collect
from mosaic.models import Paper
from mosaic.parsing import normalise_doi
from mosaic.pdf import is_pdf_file

log = logging.getLogger(__name__)

# The DOI pattern recommended by Crossref, applied to raw PDF bytes.
_DOI = rb"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+"
# Metadata fields that name the document's *own* DOI (XMP and Info dict).
_OWN_DOI = re.compile(
    rb"(?:prism:doi>|dc:identifier>(?:doi:)?|pdfx:doi>|/doi\s*\(|crossmark:DOI>)\s*("
    + _DOI
    + rb")",
    re.IGNORECASE,
)
_ANY_DOI = re.compile(_DOI)
# ScienceDirect's download name: 1-s2.0-<PII>-main.pdf
_ELSEVIER_NAME = re.compile(r"^1-s2\.0-(S[0-9X]{16})-main", re.IGNORECASE)
_SCAN_BYTES = 2 * 1024 * 1024  # head scanned for DOIs printed in the content
_CHUNK = 1024 * 1024
_OVERLAP = 512  # longer than any metadata field + DOI, so none is split unseen
_CROSSREF = "https://api.crossref.org/works"


class PdfImportError(MosaicError, ValueError):
    """Raised when a file cannot be imported (not a PDF, no DOI found, ...)."""


@dataclass
class Imported:
    paper: Paper
    dest: Path
    doi_source: str  # how the DOI was found: "given", "metadata", "filename", "content"
    original_removed: bool


def _clean(doi: bytes) -> str:
    # Raw PDF strings end with ')' or punctuation that the pattern accepts.
    return normalise_doi(doi.decode("ascii", "ignore").rstrip(").;,:/"))


def doi_from_pii(pii: str, email: str = "") -> str | None:
    """Look up the DOI registered for an Elsevier PII on Crossref."""
    params = {"filter": f"alternative-id:{pii}", "rows": "2"}
    if email:
        params["mailto"] = email
    try:
        r = httpx.get(_CROSSREF, params=params, timeout=20)
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])
    except Exception:
        log.debug("Crossref PII lookup failed for %s", pii, exc_info=True)
        return None
    return items[0]["DOI"].lower() if len(items) == 1 else None


def _metadata_doi(path: Path) -> str | None:
    """Find the document's own DOI in its metadata, anywhere in the file.

    XMP and Info dictionaries are often written near the *end* of a PDF
    (e.g. offset 3.08 MB of a 3.35 MB Elsevier file), so the whole file is
    scanned in overlapping chunks rather than just its head.
    """
    tail = b""
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            m = _OWN_DOI.search(tail + chunk)
            if m:
                return _clean(m.group(1))
            tail = chunk[-_OVERLAP:]
    return None


def detect_doi(path: Path, email: str = "") -> tuple[str, str] | None:
    """Return ``(doi, how)`` for the PDF at *path*, or None if not determinable.

    Order: the document's own DOI in its metadata; the PII in an Elsevier
    download name; a DOI in the content, only when exactly one distinct DOI
    appears (a reference list cites many, so several means "unknown").
    """
    own = _metadata_doi(path)
    if own:
        return own, "metadata"
    m = _ELSEVIER_NAME.match(path.name)
    if m:
        doi = doi_from_pii(m.group(1).upper(), email)
        if doi:
            return doi, "filename"
    with open(path, "rb") as f:
        head = f.read(_SCAN_BYTES)
    found = {_clean(d) for d in _ANY_DOI.findall(head)}
    if len(found) == 1:
        return found.pop(), "content"
    return None


def import_pdf(
    path: Path,
    cache: Cache,
    cfg: dict,
    *,
    doi: str | None = None,
    force: bool = False,
) -> Imported:
    """Move the PDF at *path* into the library under its paper's name.

    Raises
    ------
    PdfImportError
        If *path* is not a PDF, its DOI cannot be determined, or a different
        valid PDF is already filed under the target name (unless *force*).
    """
    if not path.is_file() or not is_pdf_file(path):
        raise PdfImportError(f"{path}: not a PDF")
    email = cfg.get("unpaywall", {}).get("email", "")
    if doi:
        how = "given"
        doi = normalise_doi(re.sub(r"^doi:\s*", "", doi.strip(), flags=re.IGNORECASE))
    else:
        detected = detect_doi(path, email)
        if detected is None:
            raise PdfImportError(f"{path.name}: could not determine the DOI; pass it with --doi")
        doi, how = detected

    paper = paper_for_download(doi, cache, email)
    pattern = cfg.get("filename_pattern", "{year}_{source}_{author}_{title}")
    dest = Path(cfg["download_dir"]).expanduser() / paper.safe_filename(pattern)
    if dest.resolve() == path.resolve():
        removed = False  # already in place: just record it
    else:
        if dest.exists() and is_pdf_file(dest) and not force:
            raise PdfImportError(
                f"{dest.name} is already in the library; use --force to replace it"
            )
        removed = _collect(path, str(dest))
    cache.set_download(paper.uid, str(dest), "ok")
    return Imported(paper=paper, dest=dest, doi_source=how, original_removed=removed)
