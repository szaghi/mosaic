"""Export search results to various file formats."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

from mosaic.models import Paper


def export(papers: list[Paper], path: Path) -> None:
    """Dispatch to the correct exporter based on file extension."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    dispatch = {
        ".md": _to_markdown,
        ".markdown": _to_markdown_full,
        ".csv": _to_csv,
        ".json": _to_json,
        ".bib": _to_bibtex,
        ".ris": _to_ris,
    }
    fn = dispatch.get(ext)
    if fn is None:
        raise ValueError(
            f"Unsupported format '{ext}'. Use: .md, .markdown, .csv, .json, .bib, .ris"
        )
    fn(papers, path)


# ── Markdown ──────────────────────────────────────────────────────────────────


def _to_markdown(papers: list[Paper], path: Path) -> None:
    lines = [
        "| # | Title | Authors | Year | DOI | Source | OA | PDF |",
        "|---|-------|---------|------|-----|--------|----|-----|",
    ]
    for i, p in enumerate(papers, 1):
        oa = "yes" if p.is_open_access else "no"
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
            ("Title", p.title),
            ("Authors", ", ".join(p.authors) if p.authors else ""),
            ("Year", str(p.year) if p.year else ""),
            ("DOI", p.doi or ""),
            ("arXiv ID", p.arxiv_id or ""),
            ("Journal", p.journal or ""),
            ("Volume", p.volume or ""),
            ("Issue", p.issue or ""),
            ("Pages", p.pages or ""),
            ("Source", p.source),
            ("Open Access", "yes" if p.is_open_access else "no"),
            ("Citation count", str(p.citation_count) if p.citation_count is not None else ""),
            ("PDF", p.pdf_url or ""),
            ("URL", p.url or ""),
            ("Abstract", p.abstract or ""),
        ]
        table = "| Field | Value |\n|-------|-------|\n"
        table += "\n".join(
            f"| {field} | {value.replace(chr(10), ' ')} |" for field, value in rows if value
        )
        blocks.append(f"## {i}. {p.title}\n\n{table}")
    path.write_text("\n\n---\n\n".join(blocks) + "\n", encoding="utf-8")


# ── CSV ───────────────────────────────────────────────────────────────────────


def _to_csv(papers: list[Paper], path: Path) -> None:
    fields = [
        "title",
        "authors",
        "year",
        "doi",
        "arxiv_id",
        "journal",
        "volume",
        "issue",
        "pages",
        "source",
        "is_open_access",
        "citation_count",
        "pdf_url",
        "url",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for p in papers:
            writer.writerow(
                {
                    "title": p.title,
                    "authors": "; ".join(p.authors),
                    "year": p.year or "",
                    "doi": p.doi or "",
                    "arxiv_id": p.arxiv_id or "",
                    "journal": p.journal or "",
                    "volume": p.volume or "",
                    "issue": p.issue or "",
                    "pages": p.pages or "",
                    "source": p.source,
                    "is_open_access": p.is_open_access,
                    "citation_count": p.citation_count if p.citation_count is not None else "",
                    "pdf_url": p.pdf_url or "",
                    "url": p.url or "",
                }
            )


# ── JSON ──────────────────────────────────────────────────────────────────────


def _to_json(papers: list[Paper], path: Path) -> None:
    data = [
        {
            "title": p.title,
            "authors": p.authors,
            "year": p.year,
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "abstract": p.abstract,
            "journal": p.journal,
            "volume": p.volume,
            "issue": p.issue,
            "pages": p.pages,
            "source": p.source,
            "is_open_access": p.is_open_access,
            "citation_count": p.citation_count,
            "pdf_url": p.pdf_url,
            "url": p.url,
        }
        for p in papers
    ]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ── BibTeX ────────────────────────────────────────────────────────────────────


def _to_bibtex(papers: list[Paper], path: Path) -> None:
    used: set[str] = set()
    entries = []
    for i, p in enumerate(papers, 1):
        key = _unique_key(_bibtex_key(p, i), used)
        entries.append(_bibtex_entry(p, i, key=key))
    path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def _bibtex_entry(p: Paper, index: int, key: str | None = None) -> str:
    entry_type = "article" if p.journal else "misc"
    key = key or _bibtex_key(p, index)

    fields: list[tuple[str, str]] = [("title", _brace(_bib_text(p.title)))]

    if p.authors:
        fields.append(("author", " and ".join(_bib_text(a) for a in p.authors if a)))
    if p.year:
        fields.append(("year", str(p.year)))
    if p.journal:
        fields.append(("journal", _brace(_bib_text(p.journal))))
    if p.volume:
        fields.append(("volume", _balance_braces(p.volume)))
    if p.issue:
        fields.append(("number", _balance_braces(p.issue)))
    if p.pages:
        fields.append(("pages", _balance_braces(p.pages)))
    # Identifiers and URLs are verbatim fields: only keep their braces balanced
    if p.doi:
        fields.append(("doi", _balance_braces(p.doi)))
    if p.arxiv_id:
        fields.append(("eprint", _balance_braces(p.arxiv_id)))
        fields.append(("eprinttype", "arXiv"))
        if not p.journal:
            fields.append(("howpublished", f"{{arXiv:{_balance_braces(p.arxiv_id)}}}"))
    if p.abstract:
        fields.append(("abstract", _brace(_bib_text(p.abstract))))
    if p.pdf_url:
        fields.append(("pdf", _balance_braces(p.pdf_url)))
    if p.url:
        fields.append(("url", _balance_braces(p.url)))
    if p.is_open_access:
        fields.append(("note", "Open Access"))

    body = ",\n".join(f"  {k:<14} = {{{v}}}" for k, v in fields)
    return f"@{entry_type}{{{key},\n{body}\n}}"


def _bibtex_key(p: Paper, index: int) -> str:
    """``<Family><Year><FirstTitleWord>``, e.g. ``Vaswani2017Attention``."""
    first = next((a.strip() for a in p.authors if a and a.strip()), "")
    last = _ascii_letters(_family_name(first)) or "Unknown"
    year = str(p.year) if p.year else "XXXX"
    word = _ascii_letters(p.title.split()[0] if p.title and p.title.split() else "")
    return f"{last}{year}{word}" or f"entry{index}"


def _family_name(author: str) -> str:
    """Family name of *author* in "Family, Given", "Given Family" or "Family GE" form."""
    if "," in author:
        return author.split(",", 1)[0].strip()
    tokens = author.split()
    if not tokens:
        return ""
    # PubMed style "Hinton GE": trailing run-together initials follow the family name
    if len(tokens) > 1 and tokens[-1].isupper() and tokens[-1].isalpha() and len(tokens[-1]) <= 3:
        return tokens[-2]
    return tokens[-1]


def _ascii_letters(s: str) -> str:
    """Keep only ASCII letters, transliterating accents first (Müller → Muller)."""
    folded = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z]", "", folded)


def _unique_key(key: str, used: set[str]) -> str:
    """Return *key*, or *key* + a, b, … if it was already used in this export."""
    candidate = key
    n = 0
    while candidate in used:
        n += 1
        candidate = key + (chr(ord("a") + n - 1) if n <= 26 else str(n))
    used.add(candidate)
    return candidate


def _brace(s: str) -> str:
    """Wrap in extra braces to preserve capitalisation in BibTeX."""
    return f"{{{s}}}"


def _balance_braces(s: str) -> str:
    """Drop unmatched ``{``/``}`` — BibTeX aborts the whole entry on unbalanced braces."""
    out: list[str] = []
    opens: list[int] = []
    for ch in s:
        if ch == "{":
            opens.append(len(out))
        elif ch == "}":
            if not opens:
                continue
            opens.pop()
        out.append(ch)
    for idx in reversed(opens):
        del out[idx]
    return "".join(out)


def _bib_text(s: str) -> str:
    """Make free text safe for a BibTeX field that LaTeX will typeset.

    Escapes ``& % # _`` (and ``$`` when unpaired) outside math, leaves
    ``$…$`` math segments untouched, and balances braces.
    """
    s = _balance_braces(s)
    parts = re.split(r"(?<!\\)\$", s)
    if len(parts) % 2 == 0:
        # Odd number of "$": not math, just a dollar sign somewhere
        return _escape_latex(s, dollars=True)
    return "$".join(p if i % 2 else _escape_latex(p) for i, p in enumerate(parts))


def _escape_latex(s: str, *, dollars: bool = False) -> str:
    specials = r"[&%#_$]" if dollars else r"[&%#_]"
    return re.sub(rf"(?<!\\)({specials})", r"\\\1", s)


# ── RIS ───────────────────────────────────────────────────────────────────────


def _to_ris(papers: list[Paper], path: Path) -> None:
    records = [_ris_record(p) for p in papers]
    path.write_text("\n".join(records) + "\n", encoding="utf-8")


def _ris_record(p: Paper) -> str:
    ty = "JOUR" if p.journal else "GEN"
    lines: list[str] = [f"TY  - {ty}"]

    lines.append(f"TI  - {p.title}")

    for author in p.authors:
        lines.append(f"AU  - {author}")

    if p.year:
        lines.append(f"PY  - {p.year}")
    if p.journal:
        lines.append(f"JO  - {p.journal}")
    if p.volume:
        lines.append(f"VL  - {p.volume}")
    if p.issue:
        lines.append(f"IS  - {p.issue}")
    if p.pages:
        # RIS uses SP/EP for start/end page; keep full range in SP if not splittable
        if "-" in p.pages:
            sp, _, ep = p.pages.partition("-")
            lines.append(f"SP  - {sp.strip()}")
            lines.append(f"EP  - {ep.strip()}")
        else:
            lines.append(f"SP  - {p.pages}")
    if p.doi:
        lines.append(f"DO  - {p.doi}")
    if p.url:
        lines.append(f"UR  - {p.url}")
    elif p.pdf_url:
        lines.append(f"UR  - {p.pdf_url}")
    if p.abstract:
        lines.append(f"AB  - {p.abstract}")

    lines.append("ER  - ")
    return "\n".join(lines)
