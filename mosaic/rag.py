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
# Helpers
# ---------------------------------------------------------------------------


def _paper_to_text(paper: Paper) -> str:
    """Build the text string embedded for a paper.

    Fields included (in order): title, authors (up to 10), venue, abstract.
    Year is intentionally omitted — it carries no semantic content for
    embedding-based retrieval.
    """
    parts: list[str] = []
    if paper.title:
        parts.append(f"Title: {paper.title}")
    if paper.authors:
        authors_str = "; ".join(paper.authors[:10])
        parts.append(f"Authors: {authors_str}")
    if paper.journal:
        parts.append(f"Venue: {paper.journal}")
    if paper.abstract:
        parts.append(f"Abstract: {paper.abstract}")
    return "\n".join(parts)


def _chunk_text(
    text: str,
    chunk_chars: int = 1600,
    overlap_chars: int = 200,
) -> list[tuple[str, int, int]]:
    """Split text into overlapping chunks at word boundaries.

    Parameters
    ----------
    text : str
        Input text to split.
    chunk_chars : int
        Target maximum characters per chunk (approx. chunk_chars / 4 tokens).
    overlap_chars : int
        Characters of overlap between consecutive chunks.

    Returns
    -------
    list[tuple[str, int, int]]
        List of (chunk_text, char_start, char_end) triples.
        A text shorter than chunk_chars is returned as a single chunk.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [(text, 0, len(text))]

    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        # Walk back to a word boundary unless we are at the end
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start, end))
        # Advance with overlap
        next_start = end - overlap_chars
        if next_start <= start:
            next_start = end  # guard against infinite loop
        start = next_start
    return chunks


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
) -> tuple[int, int, int]:
    """
    Embed and store papers not yet in the chunk index.

    Returns ``(newly_indexed, skipped_already_indexed, full_text_count)``.
    Papers with neither title nor abstract are silently skipped.
    full_text_count is the number of papers indexed via full PDF text.
    """
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    from mosaic import pdf as _pdf
    from mosaic.config import get_embedding_cfg
    from mosaic.embeddings import embed_texts

    emb_cfg = get_embedding_cfg(cfg)
    model = emb_cfg.get("model", "")
    if not model:
        raise ValueError(
            "No embedding model configured. Run: mosaic config --embedding-model <model-name>"
        )

    rag_cfg = cfg.get("rag", {})
    chunk_chars = int(rag_cfg.get("chunk_size", 400)) * 4
    overlap_chars = int(rag_cfg.get("chunk_overlap", 50)) * 4
    full_text_enabled = rag_cfg.get("full_text_index", True)

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
        return 0, len(papers) - len(candidates), 0

    # Warn if full_text_index is enabled but pymupdf is not installed
    if full_text_enabled and not _pdf.is_available():
        _log.warning(
            "full_text_index is enabled but pymupdf is not installed. "
            "Run: pipx inject mosaic-search pymupdf"
        )

    batch_size = 96
    full_text_count = 0

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

    # Build all chunk rows first
    all_chunk_rows: list[tuple] = []

    try:
        for paper in candidates:
            chunks: list[tuple[str, int, int]] = []

            # Try full-text extraction from downloaded PDF
            if full_text_enabled and _pdf.is_available():
                dl = cache.get_download(paper.uid)
                if dl and dl["status"] == "ok" and dl["local_path"]:
                    raw_text = _pdf.extract_text(dl["local_path"])
                    if raw_text:
                        header = _paper_to_text(paper)
                        raw_chunks = _chunk_text(raw_text, chunk_chars, overlap_chars)
                        chunks = [
                            (f"{header}\n\n{c_text}", c_start, c_end)
                            for c_text, c_start, c_end in raw_chunks
                        ]
                        full_text_count += 1

            if not chunks:
                # Fall back to metadata-only single chunk
                meta_text = _paper_to_text(paper)
                if meta_text:
                    chunks = [(meta_text, 0, len(meta_text))]

            for idx, (chunk_text, char_start, char_end) in enumerate(chunks):
                chunk_id = f"{paper.uid}::{idx}"
                all_chunk_rows.append((paper, chunk_id, idx, chunk_text, char_start, char_end))

        # Embed in batches of chunk rows
        for i in range(0, len(all_chunk_rows), batch_size):
            batch = all_chunk_rows[i : i + batch_size]
            texts = [r[3] for r in batch]
            embeddings = embed_texts(texts, emb_cfg)
            dim = len(embeddings[0])
            rows = [
                (r[1], r[0].uid, r[2], r[3], r[4], r[5], emb)
                for r, emb in zip(batch, embeddings, strict=True)
            ]
            cache.upsert_chunks_batch(rows, dim)
            if prog and task is not None:
                # Advance by number of unique papers in this batch
                unique_papers = len({r[0].uid for r in batch})
                prog.advance(task, unique_papers)
    finally:
        if prog:
            prog.stop()

    # Persist model name for future consistency checks
    cache.set_rag_meta("embedding_model", model)

    newly_indexed = len(candidates)
    skipped = len(papers) - len(candidates)
    return newly_indexed, skipped, full_text_count


def retrieve(
    query: str,
    cfg: dict,
    cache: Cache,
    *,
    k: int | None = None,
    pre_filter: list[str] | None = None,
) -> list[Paper]:
    """Embed query and return top-k papers. See retrieve_with_context for chunk texts."""
    papers, _ = _retrieve_impl(query, cfg, cache, k=k, pre_filter=pre_filter)
    return papers


def retrieve_with_context(
    query: str,
    cfg: dict,
    cache: Cache,
    *,
    k: int | None = None,
    pre_filter: list[str] | None = None,
) -> tuple[list[Paper], dict[str, str]]:
    """Embed query, de-duplicate chunks to paper level, return papers + best chunk texts."""
    return _retrieve_impl(query, cfg, cache, k=k, pre_filter=pre_filter)


def _retrieve_impl(
    query: str,
    cfg: dict,
    cache: Cache,
    *,
    k: int | None = None,
    pre_filter: list[str] | None = None,
) -> tuple[list[Paper], dict[str, str]]:
    from mosaic.config import get_embedding_cfg
    from mosaic.embeddings import embed_texts

    emb_cfg = get_embedding_cfg(cfg)
    top_k = k or cfg.get("rag", {}).get("top_k", 10)

    query_embeddings = embed_texts([query], emb_cfg)
    if not query_embeddings:
        return [], {}
    query_vec = query_embeddings[0]

    # Try vec_chunks first (new format), fall back to vec_papers (legacy)
    use_chunks = True
    chunk_results: list[tuple[str, float]] = []
    try:
        chunk_results = cache.vector_search_chunks(query_vec, top_k * 10)
    except Exception as exc:
        if "no such table" in str(exc).lower():
            use_chunks = False
        else:
            raise

    if not use_chunks or not chunk_results:
        # Legacy fallback: vec_papers
        try:
            uids = cache.vector_search(query_vec, top_k * 3 if pre_filter else top_k)
        except Exception:
            uids = []
        if not use_chunks:
            _log.warning(
                "Vector index uses the old format. "
                "Run 'mosaic index --reindex' to enable full-text chunking."
            )
        if pre_filter:
            filter_set = set(pre_filter)
            uids = [u for u in uids if u in filter_set][:top_k]
        citations_cfg = cfg.get("rag", {}).get("citations", {})
        if citations_cfg.get("enabled", False) and uids:
            alpha = float(citations_cfg.get("boost_alpha", 0.3))
            uids = _citation_boost(uids, cache, alpha, top_k)
            if citations_cfg.get("expand_neighbors", False):
                uids = _expand_neighbors(uids, cache, top_k)
        uids = uids[:top_k]
        papers = cache.get_papers_by_uids(uids)
        uid_order = {uid: i for i, uid in enumerate(uids)}
        papers.sort(key=lambda p: uid_order.get(p.uid, 9999))
        return papers, {}

    # De-duplicate chunks to paper level: keep best (lowest) distance per uid
    best: dict[str, tuple[str, float]] = {}  # uid -> (chunk_id, distance)
    for chunk_id, dist in chunk_results:
        uid = chunk_id.rsplit("::", 1)[0]
        if uid not in best or dist < best[uid][1]:
            best[uid] = (chunk_id, dist)

    # Apply pre_filter
    if pre_filter:
        filter_set = set(pre_filter)
        best = {uid: v for uid, v in best.items() if uid in filter_set}

    # Sort by best chunk distance
    uids = sorted(best, key=lambda u: best[u][1])

    # Citation boosting
    citations_cfg = cfg.get("rag", {}).get("citations", {})
    if citations_cfg.get("enabled", False) and uids:
        alpha = float(citations_cfg.get("boost_alpha", 0.3))
        uids = _citation_boost(uids, cache, alpha, top_k)
        if citations_cfg.get("expand_neighbors", False):
            uids = _expand_neighbors(uids, cache, top_k)

    uids = uids[:top_k]

    # Fetch papers and best chunk texts
    papers = cache.get_papers_by_uids(uids)
    uid_order = {uid: i for i, uid in enumerate(uids)}
    papers.sort(key=lambda p: uid_order.get(p.uid, 9999))

    best_chunk_ids = [best[uid][0] for uid in uids if uid in best]
    chunk_texts = cache.get_chunk_texts(best_chunk_ids)

    return papers, chunk_texts


def semantic_search(
    query: str,
    cache: Cache,
    cfg: dict,
    k: int = 20,
    *,
    downloaded_only: bool = False,
) -> list[Paper]:
    """Embed *query* and return the top-k cached papers ordered by similarity.

    Each returned paper has ``relevance_score`` set to
    ``1 / (1 + L2_distance)``, mapping distance to a (0, 1] similarity value.

    Raises RuntimeError if sqlite-vec is not installed, or ValueError if no
    embedding model is configured.
    """
    from mosaic.config import get_embedding_cfg
    from mosaic.embeddings import embed_texts

    emb_cfg = get_embedding_cfg(cfg)
    vecs = embed_texts([query], emb_cfg)
    if not vecs:
        return []
    query_vec = vecs[0]

    # Over-fetch when filtering by download status to absorb the loss.
    fetch_k = k * 4 if downloaded_only else k
    try:
        scored = cache.vector_search_scored(query_vec, fetch_k)
    except Exception as exc:
        if "no such table" in str(exc).lower():
            raise RuntimeError(
                "No vector index found. Run 'mosaic index' first to build the semantic search index."
            ) from exc
        raise

    if downloaded_only:
        downloaded = cache.get_downloaded_uids()
        scored = [(uid, dist) for uid, dist in scored if uid in downloaded]

    scored = scored[:k]
    uids = [uid for uid, _ in scored]
    dist_map = dict(scored)

    papers = cache.get_papers_by_uids(uids)
    uid_order = {uid: i for i, uid in enumerate(uids)}
    papers.sort(key=lambda p: uid_order.get(p.uid, 9999))
    for p in papers:
        p.relevance_score = 1.0 / (1.0 + dist_map.get(p.uid, 0.0))
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
    papers, chunk_texts = retrieve_with_context(query, cfg, cache, k=k, pre_filter=pre_filter)
    if not papers:
        return "No indexed papers found. Run `mosaic index` first.", []

    context = _build_context(papers, chunk_texts)
    template = _PROMPTS.get(mode, _PROMPTS["synthesis"])
    prompt = template.format(query=query, context=context)

    answer = _call_llm(prompt, cfg)
    return answer, papers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_context(
    papers: list[Paper],
    chunk_texts: dict[str, str] | None = None,
) -> str:
    """Build numbered context block for the LLM prompt."""
    parts = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:5]) if p.authors else "Unknown"
        if len(p.authors) > 5:
            authors += " et al."
        header = f"[{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})"
        if p.journal:
            header += f", {p.journal}"

        # Use best-matching chunk text if available, else fall back to abstract
        body = ""
        if chunk_texts:
            for chunk_id, text in chunk_texts.items():
                if chunk_id.startswith(p.uid + "::"):
                    body = text
                    break
        if not body:
            body = (p.abstract or "")[:400] or "(no abstract)"

        parts.append(f"{header}\n{body}")
    return "\n\n---\n\n".join(parts)


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
