"""Similar-paper discovery via OpenAlex related_works and Semantic Scholar recommendations."""

from __future__ import annotations

import httpx

from mosaic.models import Paper
from mosaic.services import merge_papers
from mosaic.sources.openalex import _SELECT, OpenAlexSource
from mosaic.sources.semantic_scholar import _FIELDS as _SS_FIELDS
from mosaic.sources.semantic_scholar import SemanticScholarSource

_OA_BASE = "https://api.openalex.org"
_SS_REC_BASE = "https://api.semanticscholar.org/recommendations/v1/papers/forpaper"


def find_similar(
    identifier: str,
    max_results: int = 10,
    *,
    oa_email: str = "",
    ss_api_key: str = "",
) -> tuple[str | None, list[Paper]]:
    """Return papers similar to the given DOI or arXiv ID.

    Always queries OpenAlex related_works. Also queries Semantic Scholar
    recommendations when an API key is configured. Results are deduplicated
    by Paper.uid, preferring higher citation counts and richer metadata.

    Args:
        identifier: A DOI (bare, or with ``doi:``/``DOI:`` prefix) or an
            arXiv ID with ``arxiv:``/``ARXIV:`` prefix.
        max_results: Maximum number of similar papers to return.
        oa_email: Optional email for the OpenAlex polite pool.
        ss_api_key: Optional Semantic Scholar API key. When provided, SS
            recommendations are fetched and merged with OpenAlex results.

    Returns:
        A tuple ``(seed_title, papers)`` where ``seed_title`` is the title
        of the seed paper (or ``None`` if it could not be resolved) and
        ``papers`` is the deduplicated list of similar papers.
    """
    seed_title, oa_papers = _similar_openalex(identifier, max_results, email=oa_email)
    seen: dict[str, Paper] = {p.uid: p for p in oa_papers}

    if ss_api_key:
        for p in _similar_ss(identifier, max_results, api_key=ss_api_key):
            merge_papers(seen, p)

    return seed_title, list(seen.values())


def _similar_openalex(
    identifier: str,
    max_results: int,
    email: str = "",
) -> tuple[str | None, list[Paper]]:
    """Fetch related papers from OpenAlex related_works.

    Args:
        identifier: DOI or arXiv ID of the seed paper.
        max_results: Maximum number of related papers to fetch.
        email: Optional email for the polite pool.

    Returns:
        A tuple ``(seed_title, papers)``.
    """
    params: dict = {"select": "id,title,related_works"}
    if email:
        params["mailto"] = email

    resp = httpx.get(_oa_work_url(identifier), params=params, timeout=30)
    if resp.status_code == 404:
        return None, []
    resp.raise_for_status()

    seed = resp.json()
    seed_title: str | None = seed.get("title")
    related = seed.get("related_works") or []
    if not related:
        return seed_title, []

    # Extract bare W-IDs from full URLs, cap at max_results
    w_ids = [r.rsplit("/", 1)[-1] for r in related[:max_results]]
    fetch_params: dict = {
        "filter": f"ids.openalex:{'|'.join(w_ids)}",
        "per_page": len(w_ids),
        "select": _SELECT,
    }
    if email:
        fetch_params["mailto"] = email

    resp2 = httpx.get(f"{_OA_BASE}/works", params=fetch_params, timeout=30)
    resp2.raise_for_status()

    parser = OpenAlexSource()
    papers = [parser._parse(item) for item in resp2.json().get("results", [])]
    return seed_title, papers


def _similar_ss(
    identifier: str,
    max_results: int,
    api_key: str = "",
) -> list[Paper]:
    """Fetch recommendations from Semantic Scholar.

    Args:
        identifier: DOI or arXiv ID of the seed paper.
        max_results: Maximum number of recommendations to request (capped at 500).
        api_key: Semantic Scholar API key.

    Returns:
        A list of Paper objects from the recommendations response, or an
        empty list when the paper is not found in Semantic Scholar.
    """
    headers = {"x-api-key": api_key} if api_key else {}
    resp = httpx.get(
        f"{_SS_REC_BASE}/{_ss_paper_id(identifier)}",
        params={"fields": _SS_FIELDS, "limit": min(max_results, 500)},
        headers=headers,
        timeout=30,
    )
    if resp.status_code in (400, 404):
        return []
    resp.raise_for_status()

    parser = SemanticScholarSource()
    return [parser._parse(item) for item in resp.json().get("recommendedPapers", [])]


def _oa_work_url(identifier: str) -> str:
    """Build the OpenAlex single-work URL for a DOI or arXiv ID.

    Args:
        identifier: A DOI (bare, or with ``doi:``/``DOI:`` prefix) or an
            arXiv ID with ``arxiv:``/``ARXIV:`` prefix.

    Returns:
        The OpenAlex entity URL for direct lookup.
    """
    ident = identifier.strip()
    if ident.lower().startswith("arxiv:"):
        return f"{_OA_BASE}/works/https://arxiv.org/abs/{ident[6:]}"
    doi = ident.removeprefix("doi:").removeprefix("DOI:")
    return f"{_OA_BASE}/works/https://doi.org/{doi}"


def _ss_paper_id(identifier: str) -> str:
    """Convert a DOI or arXiv ID to the Semantic Scholar paper ID format.

    Args:
        identifier: A DOI (bare, or with ``doi:``/``DOI:`` prefix) or an
            arXiv ID with ``arxiv:``/``ARXIV:`` prefix.

    Returns:
        A string like ``"DOI:10.xxx"`` or ``"ARXIV:2106.xxx"``.
    """
    ident = identifier.strip()
    if ident.lower().startswith("arxiv:"):
        return f"ARXIV:{ident[6:]}"
    doi = ident.removeprefix("doi:").removeprefix("DOI:")
    return f"DOI:{doi}"
