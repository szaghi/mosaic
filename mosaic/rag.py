"""RAG pipeline: index, retrieve, ask."""

from __future__ import annotations

import logging
import textwrap

import httpx

from mosaic.db import Cache
from mosaic.models import Paper

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_PROMPTS: dict[str, str] = {
    "synthesis": textwrap.dedent("""\
        You are a research assistant synthesising scientific literature.
        Based solely on the papers provided below, write a comprehensive synthesis
        of the state of the art regarding: "{query}"

        Cover: main approaches and methods, key findings, areas of consensus,
        notable disagreements or open debates.
        Cite papers using their number in square brackets, e.g. [1] or [2][4].
        Do not cite papers not listed below. Keep the response focused and structured.

        Papers:
        {context}
    """),
    "gaps": textwrap.dedent("""\
        You are a research analyst identifying gaps in the scientific literature.
        Based solely on the papers provided below, identify open problems,
        unexplored directions, contradictions, and methodological limitations
        related to: "{query}"

        For each gap, provide evidence from the papers. Use [n] citations.
        Do not speculate beyond what the papers support.

        Papers:
        {context}
    """),
    "compare": textwrap.dedent("""\
        You are a research analyst comparing scientific papers.
        Based solely on the papers provided below, produce a structured comparison
        related to: "{query}"

        Compare across: methods/approaches, datasets used, evaluation metrics,
        key results, and trade-offs. Present as a structured analysis with a
        summary table where appropriate. Use [n] citations.

        Papers:
        {context}
    """),
    "extract": textwrap.dedent("""\
        You are a research assistant extracting structured information from papers.
        For each paper listed below, extract the following fields if present:
        Task, Method, Dataset, Metric, Key Result.

        Output as a structured list, one entry per paper, using [n] to reference each.
        If a field is not mentioned in the abstract, write "–".

        Papers:
        {context}
    """),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def index_papers(
    papers: list[Paper],
    cfg: dict,
    cache: Cache,
    *,
    reindex: bool = False,
    progress: bool = True,
) -> tuple[int, int]:
    """
    Embed and store papers not yet in the vector index.

    Returns ``(newly_indexed, skipped_already_indexed)``.
    Papers with neither title nor abstract are silently skipped.
    """
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    from mosaic.config import get_embedding_cfg
    from mosaic.embeddings import embed_texts

    emb_cfg = get_embedding_cfg(cfg)
    model = emb_cfg.get("model", "")
    if not model:
        raise ValueError(
            "No embedding model configured. Run: mosaic config --embedding-model <model-name>"
        )

    # Detect model change
    stored_model = cache.get_rag_meta("embedding_model")
    if stored_model and stored_model != model and not reindex:
        raise ValueError(
            f"Embedding model changed: stored={stored_model!r}, current={model!r}. "
            "Run 'mosaic index --reindex' to rebuild the vector index."
        )
    if reindex:
        cache.rebuild_vec_table()

    already_indexed = cache.get_indexed_uids()

    # Filter candidates
    candidates = [
        p for p in papers if (p.title or p.abstract) and (reindex or p.uid not in already_indexed)
    ]

    if not candidates:
        return 0, len(papers) - len(candidates)

    texts = [(p.title or "") + " " + (p.abstract or "") for p in candidates]

    batch_size = 96
    newly_indexed = 0

    if progress:
        prog = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            transient=True,
        )
        task = prog.add_task(f"[cyan]Embedding[/cyan] [dim]({model})[/dim]", total=len(candidates))
        prog.start()
    else:
        prog = None
        task = None

    try:
        for i in range(0, len(candidates), batch_size):
            batch_papers = candidates[i : i + batch_size]
            batch_texts = texts[i : i + batch_size]
            embeddings = embed_texts(batch_texts, emb_cfg)
            dim = len(embeddings[0])
            rows = [(p.uid, emb) for p, emb in zip(batch_papers, embeddings, strict=True)]
            cache.upsert_embeddings_batch(rows, dim)
            newly_indexed += len(batch_papers)
            if prog and task is not None:
                prog.advance(task, len(batch_papers))
    finally:
        if prog:
            prog.stop()

    # Persist model name for future consistency checks
    cache.set_rag_meta("embedding_model", model)

    skipped = len(papers) - len(candidates)
    return newly_indexed, skipped


def retrieve(
    query: str,
    cfg: dict,
    cache: Cache,
    *,
    k: int | None = None,
    pre_filter: list[str] | None = None,
) -> list[Paper]:
    """
    Embed *query* and return the top-k most similar Paper objects.

    When ``cfg["rag"]["citations"]["enabled"]`` is True, applies citation
    graph boosting: papers that share citation edges with other top results
    are promoted using a reciprocal-rank * citation-factor score.

    *pre_filter*: optional list of UIDs to restrict the search to a subset.
    """
    from mosaic.config import get_embedding_cfg
    from mosaic.embeddings import embed_texts

    emb_cfg = get_embedding_cfg(cfg)
    top_k = k or cfg.get("rag", {}).get("top_k", 10)

    query_embeddings = embed_texts([query], emb_cfg)
    if not query_embeddings:
        return []
    query_vec = query_embeddings[0]

    uids = cache.vector_search(query_vec, top_k * 3 if pre_filter else top_k)

    if pre_filter:
        filter_set = set(pre_filter)
        uids = [u for u in uids if u in filter_set][:top_k]

    # ── Citation graph boosting ───────────────────────────────────────────────
    citations_cfg = cfg.get("rag", {}).get("citations", {})
    if citations_cfg.get("enabled", False) and uids:
        alpha = float(citations_cfg.get("boost_alpha", 0.3))
        uids = _citation_boost(uids, cache, alpha, top_k)

        if citations_cfg.get("expand_neighbors", False):
            uids = _expand_neighbors(uids, cache, top_k)

    uids = uids[:top_k]
    papers = cache.get_papers_by_uids(uids)
    # Preserve post-boost order
    uid_order = {uid: i for i, uid in enumerate(uids)}
    papers.sort(key=lambda p: uid_order.get(p.uid, 9999))
    return papers


def ask(
    query: str,
    cfg: dict,
    cache: Cache,
    *,
    mode: str = "synthesis",
    k: int | None = None,
    pre_filter: list[str] | None = None,
) -> tuple[str, list[Paper]]:
    """
    Full RAG pipeline: retrieve → build prompt → call LLM → return answer.

    Returns ``(answer_text, retrieved_papers)``.
    """
    papers = retrieve(query, cfg, cache, k=k, pre_filter=pre_filter)
    if not papers:
        return "No indexed papers found. Run `mosaic index` first.", []

    context = _build_context(papers)
    template = _PROMPTS.get(mode, _PROMPTS["synthesis"])
    prompt = template.format(query=query, context=context)

    answer = _call_llm(prompt, cfg)
    return answer, papers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_context(papers: list[Paper]) -> str:
    lines = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:3]) if p.authors else "Unknown"
        if len(p.authors) > 3:
            authors += " et al."
        abstract_snippet = (p.abstract or "")[:400]
        lines.append(
            f"[{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})\n    {abstract_snippet}"
        )
    return "\n\n".join(lines)


def _citation_boost(
    uids: list[str],
    cache: Cache,
    alpha: float,
    top_k: int,
) -> list[str]:
    """Re-rank *uids* by combining reciprocal rank with citation link count.

    Score for position *i*::

        score(i) = (1 / (i + 1)) * (1 + alpha * citation_links(uid_i, uid_set))

    Papers with more cross-citations to other retrieved papers rise in rank.
    When ``alpha=0`` the original cosine order is preserved.

    Args:
        uids: UIDs in cosine-similarity order (best first).
        cache: Local SQLite cache for citation lookups.
        alpha: Citation boost weight.  0 = pure cosine order.
        top_k: Number of UIDs to retain after re-ranking.

    Returns:
        Re-ranked list of UIDs, length ≤ ``len(uids)``.
    """
    uid_set = set(uids)
    scored: list[tuple[float, str]] = []
    for i, uid in enumerate(uids):
        rr = 1.0 / (i + 1)
        links = cache.get_citation_links(uid, uid_set - {uid})
        scored.append((rr * (1.0 + alpha * links), uid))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [uid for _, uid in scored]


def _expand_neighbors(uids: list[str], cache: Cache, top_k: int) -> list[str]:
    """Extend *uids* with 1-hop citation neighbors present in the local cache.

    Adds neighbors of the top-*top_k* results that are not already in *uids*,
    preserving the existing order and appending new candidates at the end.

    Args:
        uids: Current UID list (post-boost).
        cache: Local SQLite cache.
        top_k: How many top UIDs to explore for neighbors.

    Returns:
        Extended UID list with neighbors appended (deduplicated).
    """
    seen = set(uids)
    extended = list(uids)
    for uid in uids[:top_k]:
        for neighbor in cache.get_citation_neighbors(uid):
            if neighbor not in seen:
                seen.add(neighbor)
                extended.append(neighbor)
    return extended


def _call_llm(prompt: str, cfg: dict) -> str:
    """Call the configured LLM generator and return the response text."""
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "").lower()
    api_key = llm_cfg.get("api_key", "")
    model = llm_cfg.get("model", "")
    base_url = llm_cfg.get("base_url", "").rstrip("/")

    if not api_key or not provider:
        raise ValueError(
            "No LLM configured. Run: mosaic config --llm-provider openai --llm-api-key KEY --llm-model MODEL"
        )

    if not model:
        model = "gpt-4o-mini" if provider == "openai" else "claude-haiku-4-5-20251001"

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
        resp = httpx.post(url, headers=headers, json=payload, timeout=180)
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
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = httpx.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    raise ValueError(f"Unknown LLM provider: {provider!r}")
