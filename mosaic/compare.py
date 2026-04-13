"""Multi-paper comparative analysis: LLM-based extraction with metadata fallback."""

from __future__ import annotations

import csv
import io
import json
import logging

import httpx

from mosaic.models import Paper

_log = logging.getLogger(__name__)

DEFAULT_DIMENSIONS = ["method", "dataset", "metric", "result"]


# ── Public API ────────────────────────────────────────────────────────────────


def compare_papers(
    papers: list[Paper],
    dimensions: list[str],
    cfg: dict,
) -> list[dict[str, str]]:
    """Extract comparison dimensions for each paper.

    Tries the configured LLM when available.  Falls back to metadata-only
    extraction (year, source, journal, DOI) when no LLM is configured or when
    the LLM call fails.

    Args:
        papers: Papers to compare.
        dimensions: Dimension names to extract (e.g. ``["method", "dataset"]``).
        cfg: Loaded mosaic config dict.

    Returns:
        List of dicts with exactly *dimensions* as keys, one dict per paper.
        Missing or unavailable fields are ``"-"``.
    """
    llm_cfg = cfg.get("llm", {})
    if llm_cfg.get("api_key") and llm_cfg.get("provider"):
        try:
            return _llm_extract(papers, dimensions, llm_cfg)
        except Exception as exc:
            _log.warning("LLM comparison failed (%s) — using metadata fallback", exc)
    return _metadata_fallback(papers, dimensions)


# ── Extractors ────────────────────────────────────────────────────────────────


_META_DIMS = {"year", "source", "journal", "doi", "authors", "citations", "citation_count"}


def _metadata_fallback(papers: list[Paper], dimensions: list[str]) -> list[dict[str, str]]:
    """Extract only what is directly available from cached metadata."""
    rows: list[dict[str, str]] = []
    for p in papers:
        row: dict[str, str] = {}
        for dim in dimensions:
            dl = dim.lower()
            if dl == "year":
                row[dim] = str(p.year) if p.year else "–"
            elif dl == "source":
                row[dim] = p.source or "–"
            elif dl == "journal":
                row[dim] = p.journal or "–"
            elif dl == "doi":
                row[dim] = p.doi or "–"
            elif dl == "authors":
                row[dim] = p.short_authors or "–"
            elif dl in ("citations", "citation_count", "cited"):
                row[dim] = str(p.citation_count) if p.citation_count is not None else "–"
            else:
                row[dim] = "–"
        rows.append(row)
    return rows


def _llm_extract(
    papers: list[Paper],
    dimensions: list[str],
    llm_cfg: dict,
) -> list[dict[str, str]]:
    """Send papers to the configured LLM in batches to extract *dimensions*."""
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    provider = llm_cfg.get("provider", "").lower()
    api_key = llm_cfg["api_key"]
    model = llm_cfg.get("model") or _default_model(provider)
    base_url = llm_cfg.get("base_url", "").rstrip("/")
    dims_str = ", ".join(f'"{d}"' for d in dimensions)

    rows: list[dict[str, str]] = []
    batch_size = 20

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Comparing papers[/cyan] [dim]({model})[/dim]",
            total=len(papers),
        )
        for i in range(0, len(papers), batch_size):
            batch = papers[i : i + batch_size]
            snippets = "\n".join(
                f"{j + 1}. Title: {p.title}\n   Abstract: {(p.abstract or '')[:300]}"
                for j, p in enumerate(batch)
            )
            prompt = (
                f"For each paper below extract the following dimensions: {dims_str}.\n"
                f"Return a JSON array of exactly {len(batch)} objects. "
                f"Each object must have exactly these keys: {dims_str}. "
                f'Use "-" when a dimension cannot be inferred from the title or abstract.\n\n'
                f"{snippets}"
            )
            raw = _call_llm(provider, api_key, model, prompt, base_url=base_url)
            extracted = _parse_obj_list(raw, len(batch), dimensions)
            rows.extend(extracted)
            progress.advance(task, len(batch))

    return rows


# ── LLM helpers ──────────────────────────────────────────────────────────────


def _call_llm(
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    base_url: str = "",
) -> str:
    """Call the configured LLM and return the raw response text."""
    if provider == "openai" or base_url:
        url = (
            f"{base_url}/chat/completions"
            if base_url
            else "https://api.openai.com/v1/chat/completions"
        )
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if not base_url:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = httpx.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    raise ValueError(f"Unknown LLM provider: {provider!r}")


def _parse_obj_list(
    content: str,
    expected: int,
    dimensions: list[str],
) -> list[dict[str, str]]:
    """Parse an LLM JSON response into a list of dimension dicts.

    Args:
        content: Raw LLM response string (expected to be JSON).
        expected: Number of objects expected in the array.
        dimensions: Ordered list of dimension keys.

    Returns:
        List of dicts with *dimensions* as keys; shorter than *expected* only
        if there is a parse error (padded with ``"-"`` in that case).

    Raises:
        ValueError: If the content is not valid JSON.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON: {content[:200]!r}") from exc

    # Unwrap dict wrappers: {"papers": [...], "results": [...], ...}
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
        else:
            raise ValueError(f"No array found in LLM response: {list(data.keys())}")

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")

    rows: list[dict[str, str]] = []
    for item in data[:expected]:
        if isinstance(item, dict):
            row = {d: str(item.get(d, "–")) for d in dimensions}
        else:
            row = dict.fromkeys(dimensions, "–")
        rows.append(row)

    # Pad when model returns fewer items than expected
    while len(rows) < expected:
        rows.append(dict.fromkeys(dimensions, "–"))

    return rows


def _default_model(provider: str) -> str:
    if provider == "openai":
        return "gpt-4o-mini"
    if provider == "anthropic":
        return "claude-haiku-4-5-20251001"
    return ""


# ── Output formatters ─────────────────────────────────────────────────────────


def format_markdown(
    papers: list[Paper],
    rows: list[dict[str, str]],
    dimensions: list[str],
) -> str:
    """Render the comparison as a Markdown table.

    Args:
        papers: Source papers (for title, year, authors).
        rows: Extracted dimension values, one dict per paper.
        dimensions: Ordered list of dimension keys.

    Returns:
        Markdown table string.
    """
    fixed_headers = ["#", "Title", "Year", "Authors"]
    dim_headers = [d.title() for d in dimensions]
    all_headers = fixed_headers + dim_headers
    sep = ["---"] * len(all_headers)

    lines = [
        "| " + " | ".join(all_headers) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for i, (p, row) in enumerate(zip(papers, rows, strict=False), 1):
        year = str(p.year) if p.year else "–"
        cells = [str(i), p.title[:60], year, p.short_authors] + [
            row.get(d, "–") for d in dimensions
        ]
        # Escape pipe characters inside cells
        cells = [c.replace("|", "\\|") for c in cells]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def format_csv(
    papers: list[Paper],
    rows: list[dict[str, str]],
    dimensions: list[str],
) -> str:
    """Render the comparison as CSV.

    Args:
        papers: Source papers.
        rows: Extracted dimension values.
        dimensions: Ordered list of dimension keys.

    Returns:
        CSV string with header row.
    """
    buf = io.StringIO()
    fixed = ["#", "title", "year", "authors"]
    fieldnames = fixed + dimensions
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for i, (p, row) in enumerate(zip(papers, rows, strict=False), 1):
        record: dict[str, str | int] = {
            "#": i,
            "title": p.title,
            "year": p.year or "",
            "authors": p.short_authors,
        }
        record.update(row)
        writer.writerow(record)
    return buf.getvalue()


def format_json_output(
    papers: list[Paper],
    rows: list[dict[str, str]],
    dimensions: list[str],
) -> str:
    """Render the comparison as a JSON array.

    Args:
        papers: Source papers.
        rows: Extracted dimension values.
        dimensions: Ordered list of dimension keys (present for type-checking).

    Returns:
        JSON array string, one object per paper.
    """
    out = []
    for i, (p, row) in enumerate(zip(papers, rows, strict=False), 1):
        entry: dict = {
            "#": i,
            "title": p.title,
            "year": p.year,
            "authors": p.short_authors,
            "doi": p.doi,
        }
        entry.update(row)
        out.append(entry)
    return json.dumps(out, indent=2, ensure_ascii=False)
