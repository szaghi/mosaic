"""Shared business logic used by both the CLI and the web UI."""

from __future__ import annotations

from mosaic.models import Paper, SearchFilters


def build_filters(
    year: str = "",
    author: str | list[str] = "",
    journal: str = "",
    field: str = "all",
    raw_query: str = "",
    require_year: bool = False,
) -> tuple[SearchFilters | None, str | None]:
    """Build a ``SearchFilters`` from user input.

    Args:
        year: Year string (``"2020"``, ``"2020-2024"``, or ``"2020,2022,2024"``).
        author: Comma-separated author string **or** a list of author names.
        journal: Journal name substring.
        field: ``"title"``, ``"abstract"``, or ``"all"``.
        raw_query: Raw query override.
        require_year: With a year filter, exclude papers whose year is unknown.

    Returns:
        A tuple ``(filters_or_None, warning_or_None)``.  The warning is set
        when the year string cannot be parsed; other fields are still applied.
    """
    # Normalise author to a list
    if isinstance(author, str):
        authors = [a.strip() for a in author.split(",") if a.strip()] if author else []
    else:
        authors = list(author)

    if not any([year, authors, journal, field != "all", raw_query]):
        return None, None

    filters = SearchFilters(
        authors=authors,
        journal=journal,
        field=field,
        raw_query=raw_query,
        require_year=require_year,
    )
    warning: str | None = None

    if year:
        try:
            parsed = SearchFilters.parse_year(year)
            filters.year_from = parsed.year_from
            filters.year_to = parsed.year_to
            filters.years = parsed.years
        except ValueError:
            warning = f'Invalid year format "{year}". Use: 2020, 2020-2024, or 2020,2022,2024'

    return filters, warning


def filter_papers(
    papers: list[Paper],
    *,
    oa_only: bool = False,
    pdf_only: bool = False,
    sort_by: str = "",
) -> list[Paper]:
    """Apply post-processing filters to a list of papers.

    Args:
        papers: Papers to filter (not mutated; a new list is returned).
        oa_only: Keep only open-access papers (or those with a PDF URL).
        pdf_only: Keep only papers that have a PDF URL.
        sort_by: ``"citations"`` (most cited first) or ``"year"`` (newest first).

    Returns:
        A filtered (and optionally sorted) list of papers.
    """
    result = list(papers)
    if oa_only:
        result = [p for p in result if p.is_open_access or p.pdf_url]
    if pdf_only:
        result = [p for p in result if p.pdf_url]
    if sort_by == "citations":
        result.sort(key=lambda p: p.citation_count or 0, reverse=True)
    elif sort_by == "year":
        result.sort(key=lambda p: p.year or 0, reverse=True)
    return result


def sort_by_relevance(query: str, papers: list[Paper], cfg: dict) -> list[Paper]:
    """Score and sort *papers* by relevance to *query* (highest first).

    Uses BM25 by default; falls back to an LLM scorer when ``cfg["llm"]`` is configured.
    """
    from mosaic.ranking import score_papers

    scored = score_papers(query, papers, cfg)
    return sorted(scored, key=lambda p: p.relevance_score or 0.0, reverse=True)


def merge_papers(seen: dict[str, Paper], paper: Paper) -> None:
    """Merge *paper* into *seen*, preferring richer metadata.

    Mirrors the field-level rules of the SQLite upsert (``db.upsert``) so that
    in-memory results (exports, Zotero/Obsidian pushes) are as rich as the
    cached record:

    - abstract       : keep the longer version
    - pdf_url        : keep the existing value, fill if empty
    - is_open_access : True supersedes False
    - citation_count : keep the higher value
    - authors        : keep the longer list
    - identifiers, year, journal, volume, issue, pages, url, openalex_id : fill if empty
    - title, source  : keep the first-recorded value
    """
    uid = paper.uid
    if uid not in seen:
        seen[uid] = paper
        return
    existing = seen[uid]
    if paper.abstract and len(paper.abstract) > len(existing.abstract or ""):
        existing.abstract = paper.abstract
    if paper.is_open_access:
        existing.is_open_access = True
    if paper.citation_count is not None and (
        existing.citation_count is None or paper.citation_count > existing.citation_count
    ):
        existing.citation_count = paper.citation_count
    if len(paper.authors) > len(existing.authors):
        existing.authors = list(paper.authors)
    for attr in (
        "pdf_url",
        "doi",
        "arxiv_id",
        "pii",
        "year",
        "journal",
        "volume",
        "issue",
        "pages",
        "url",
        "openalex_id",
    ):
        if getattr(existing, attr) in (None, "") and getattr(paper, attr) not in (None, ""):
            setattr(existing, attr, getattr(paper, attr))


# ---------------------------------------------------------------------------
# Result post-processing
# ---------------------------------------------------------------------------

SORT_CHOICES = ("citations", "year", "relevance")
FIELD_CHOICES = ("all", "title", "abstract")


def post_process(
    papers: list[Paper],
    *,
    query: str,
    cfg: dict,
    oa_only: bool = False,
    pdf_only: bool = False,
    sort_by: str = "",
) -> list[Paper]:
    """Apply OA/PDF filters and sorting, including relevance ranking.

    Raises:
        ValueError: when *sort_by* is not one of :data:`SORT_CHOICES`.
    """
    if sort_by and sort_by not in SORT_CHOICES:
        raise ValueError(f'Unknown sort "{sort_by}". Use: {", ".join(SORT_CHOICES)}')
    papers = filter_papers(
        papers,
        oa_only=oa_only,
        pdf_only=pdf_only,
        sort_by=sort_by if sort_by != "relevance" else "",
    )
    if sort_by == "relevance":
        papers = sort_by_relevance(query, papers, cfg)
    return papers


# ---------------------------------------------------------------------------
# Cached-paper selection (used by index / ask / chat / compare / bulk get)
# ---------------------------------------------------------------------------


def _doi_uid(doi: str) -> str:
    from mosaic.parsing import normalise_doi

    bare = normalise_doi(doi) or doi.strip()
    return Paper(title=bare, doi=bare, source="").uid


def lookup_dois(cache, dois: list[str]) -> list[Paper]:
    """Return the cached papers for *dois* (unknown DOIs are skipped, no duplicates)."""
    found: dict[str, Paper] = {}
    for doi in dois:
        paper = cache.get_by_uid(_doi_uid(doi))
        if paper is not None:
            found.setdefault(paper.uid, paper)
    return list(found.values())


def papers_for_dois(cache, dois: list[str]) -> list[Paper]:
    """Return one paper per DOI: the cached record when known, else a bare stub."""
    from mosaic.parsing import normalise_doi

    papers: list[Paper] = []
    seen: set[str] = set()
    for doi in dois:
        bare = normalise_doi(doi) or doi.strip()
        stub = Paper(title=bare, doi=bare, source="manual")
        if stub.uid in seen:
            continue
        seen.add(stub.uid)
        papers.append(cache.get_by_uid(stub.uid) or stub)
    return papers


def select_cached_papers(
    cache,
    *,
    query: str = "",
    dois: list[str] | None = None,
    year: str = "",
) -> list[Paper] | None:
    """Cached papers matching **all** the given constraints.

    Returns ``None`` when no constraint is given (meaning "the whole library"),
    and a possibly empty list otherwise — callers must not confuse the two.

    Raises:
        ValueError: when *year* cannot be parsed.
    """
    if not query and dois is None and not year:
        return None

    candidates: list[Paper] | None = None
    if dois is not None:
        candidates = lookup_dois(cache, dois)
    if query:
        matches = cache.search_local(query)
        if candidates is None:
            candidates = matches
        else:
            keep = {p.uid for p in matches}
            candidates = [p for p in candidates if p.uid in keep]
    if year:
        filters, warning = build_filters(year=year)
        if warning:
            raise ValueError(warning)
        base = candidates if candidates is not None else cache.get_all_papers()
        candidates = [p for p in base if filters is None or filters.match(p)]
    return candidates or []


def subset_uids(
    cache,
    *,
    query: str = "",
    dois: list[str] | None = None,
    year: str = "",
) -> list[str] | None:
    """UIDs for :func:`select_cached_papers` (``None`` = no restriction)."""
    papers = select_cached_papers(cache, query=query, dois=dois, year=year)
    return None if papers is None else [p.uid for p in papers]


# ---------------------------------------------------------------------------
# RAG answers
# ---------------------------------------------------------------------------

RAG_MODES = ("synthesis", "gaps", "compare", "extract")


def format_answer(question: str, mode: str, answer: str, papers: list[Paper], fmt: str) -> str:
    """Render a RAG answer with its references as Markdown (``"md"``) or JSON (``"json"``)."""
    if fmt == "json":
        import json

        data = {
            "question": question,
            "mode": mode,
            "answer": answer,
            "sources": [
                {"title": p.title, "authors": p.authors, "year": p.year, "doi": p.doi}
                for p in papers
            ],
        }
        return json.dumps(data, indent=2, default=str)
    lines = [f"# {question}\n", f"*Mode: {mode}*\n\n", answer, "\n\n## References\n"]
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:3]) if p.authors else "Unknown"
        lines.append(f"- [{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Citation network
# ---------------------------------------------------------------------------


def analyse_network(
    cache,
    *,
    query: str = "",
    depth: int = 2,
    min_connections: int = 1,
    cluster: bool = False,
) -> dict:
    """Build the (sub)graph used by ``mosaic network`` and the web UI.

    Returns a dict with ``nodes``, ``adj``, ``deg``, ``papers`` (uid → Paper)
    and ``clusters`` (``None`` unless *cluster*).

    Raises:
        LookupError: with a user-facing message when there is nothing to show.
    """
    from mosaic.network import (
        build_adj,
        compute_degree,
        louvain_clusters,
        subgraph_from_seeds,
    )

    edges = cache.get_all_citation_edges()
    if not edges:
        raise LookupError("No citation edges found. Run `mosaic index --enrich-citations` first.")
    adj = build_adj(edges)

    if query:
        seeds = [p.uid for p in cache.search_local(query) if p.uid in adj]
        if not seeds:
            raise LookupError(f"No cached papers matching {query!r} found in the citation graph.")
        nodes = subgraph_from_seeds(adj, seeds, depth)
    else:
        nodes = set(adj.keys())

    deg = compute_degree(adj, nodes)
    nodes = {uid for uid in nodes if deg.get(uid, 0) >= min_connections}
    if not nodes:
        raise LookupError("No papers meet the minimum-connections threshold.")

    # Degrees on the filtered subgraph
    deg = compute_degree(adj, nodes)
    papers = {p.uid: p for p in cache.get_papers_by_uids(list(nodes))}
    clusters = louvain_clusters(nodes, adj) if cluster else None
    return {"nodes": nodes, "adj": adj, "deg": deg, "papers": papers, "clusters": clusters}
