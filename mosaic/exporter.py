"""Export search results to various file formats."""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path
from mosaic.models import Paper


def export(papers: list[Paper], path: Path) -> None:
    """Dispatch to the correct exporter based on file extension."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    dispatch = {
        ".md":       _to_markdown,
        ".markdown": _to_markdown_full,
        ".csv":      _to_csv,
        ".json":     _to_json,
        ".bib":      _to_bibtex,
    }
    fn = dispatch.get(ext)
    if fn is None:
        raise ValueError(f"Unsupported format '{ext}'. Use: .md, .markdown, .csv, .json, .bib")
    fn(papers, path)


# ── Markdown ──────────────────────────────────────────────────────────────────

def _to_markdown(papers: list[Paper], path: Path) -> None:
    lines = [
        "| # | Title | Authors | Year | DOI | Source | OA | PDF |",
        "|---|-------|---------|------|-----|--------|----|-----|",
    ]
    for i, p in enumerate(papers, 1):
        oa  = "yes" if p.is_open_access else "no"
        pdf = p.pdf_url or ""
        doi = p.doi or ""
        lines.append(
            f"| {i} | {p.title} | {p.short_authors} | {p.year or ''} "
            f"| {doi} | {p.source} | {oa} | {pdf} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Markdown (detailed) ───────────────────────────────────────────────────────

def _to_markdown_full(papers: list[Paper], path: Path) -> None:
    blocks = []
    for i, p in enumerate(papers, 1):
        rows: list[tuple[str, str]] = [
            ("Title",        p.title),
            ("Authors",      ", ".join(p.authors) if p.authors else ""),
            ("Year",         str(p.year) if p.year else ""),
            ("DOI",          p.doi or ""),
            ("arXiv ID",     p.arxiv_id or ""),
            ("Journal",      p.journal or ""),
            ("Volume",       p.volume or ""),
            ("Issue",        p.issue or ""),
            ("Pages",        p.pages or ""),
            ("Source",          p.source),
            ("Open Access",     "yes" if p.is_open_access else "no"),
            ("Citation count",  str(p.citation_count) if p.citation_count is not None else ""),
            ("PDF",             p.pdf_url or ""),
            ("URL",             p.url or ""),
            ("Abstract",        p.abstract or ""),
        ]
        table = "| Field | Value |\n|-------|-------|\n"
        table += "\n".join(
            f"| {field} | {value.replace(chr(10), ' ')} |"
            for field, value in rows
            if value
        )
        blocks.append(f"## {i}. {p.title}\n\n{table}")
    path.write_text("\n\n---\n\n".join(blocks) + "\n", encoding="utf-8")


# ── CSV ───────────────────────────────────────────────────────────────────────

def _to_csv(papers: list[Paper], path: Path) -> None:
    fields = ["title", "authors", "year", "doi", "arxiv_id",
              "journal", "volume", "issue", "pages",
              "source", "is_open_access", "citation_count", "pdf_url", "url"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for p in papers:
            writer.writerow({
                "title":          p.title,
                "authors":        "; ".join(p.authors),
                "year":           p.year or "",
                "doi":            p.doi or "",
                "arxiv_id":       p.arxiv_id or "",
                "journal":        p.journal or "",
                "volume":         p.volume or "",
                "issue":          p.issue or "",
                "pages":          p.pages or "",
                "source":         p.source,
                "is_open_access": p.is_open_access,
                "citation_count": p.citation_count if p.citation_count is not None else "",
                "pdf_url":        p.pdf_url or "",
                "url":            p.url or "",
            })


# ── JSON ──────────────────────────────────────────────────────────────────────

def _to_json(papers: list[Paper], path: Path) -> None:
    data = [
        {
            "title":          p.title,
            "authors":        p.authors,
            "year":           p.year,
            "doi":            p.doi,
            "arxiv_id":       p.arxiv_id,
            "abstract":       p.abstract,
            "journal":        p.journal,
            "volume":         p.volume,
            "issue":          p.issue,
            "pages":          p.pages,
            "source":         p.source,
            "is_open_access": p.is_open_access,
            "citation_count": p.citation_count,
            "pdf_url":        p.pdf_url,
            "url":            p.url,
        }
        for p in papers
    ]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ── BibTeX ────────────────────────────────────────────────────────────────────

def _to_bibtex(papers: list[Paper], path: Path) -> None:
    entries = [_bibtex_entry(p, i) for i, p in enumerate(papers, 1)]
    path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def _bibtex_entry(p: Paper, index: int) -> str:
    entry_type = "article" if p.journal else "misc"
    key = _bibtex_key(p, index)

    fields: list[tuple[str, str]] = [("title", _brace(p.title))]

    if p.authors:
        fields.append(("author", " and ".join(p.authors)))
    if p.year:
        fields.append(("year", str(p.year)))
    if p.journal:
        fields.append(("journal", _brace(p.journal)))
    if p.volume:
        fields.append(("volume", p.volume))
    if p.issue:
        fields.append(("number", p.issue))
    if p.pages:
        fields.append(("pages", p.pages))
    if p.doi:
        fields.append(("doi", p.doi))
    if p.arxiv_id:
        fields.append(("eprint",      p.arxiv_id))
        fields.append(("eprinttype",  "arXiv"))
        if not p.journal:
            fields.append(("howpublished", f"{{arXiv:{p.arxiv_id}}}"))
    if p.abstract:
        fields.append(("abstract", _brace(p.abstract)))
    if p.pdf_url:
        fields.append(("pdf", p.pdf_url))
    if p.url:
        fields.append(("url", p.url))
    if p.is_open_access:
        fields.append(("note", "Open Access"))

    body = ",\n".join(f"  {k:<14} = {{{v}}}" for k, v in fields)
    return f"@{entry_type}{{{key},\n{body}\n}}"


def _bibtex_key(p: Paper, index: int) -> str:
    last = p.authors[0].split()[-1] if p.authors else "Unknown"
    last = re.sub(r"[^A-Za-z]", "", last)
    year = str(p.year) if p.year else "XXXX"
    word = re.sub(r"[^A-Za-z]", "", (p.title.split()[0] if p.title else ""))
    return f"{last}{year}{word}" or f"entry{index}"


def _brace(s: str) -> str:
    """Wrap in extra braces to preserve capitalisation in BibTeX."""
    return f"{{{s}}}"
