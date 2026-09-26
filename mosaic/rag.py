"""RAG pipeline: index, retrieve, ask."""

from __future__ import annotations

import logging
import re
import sqlite3
import textwrap

import httpx

from mosaic.db import VEC_MAX_K, Cache
from mosaic.models import Paper

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-facing messages (shown verbatim by the CLI and the web UI)
# ---------------------------------------------------------------------------

NO_INDEX_MESSAGE = "No indexed papers found. Run `mosaic index` first."
NO_SUBSET_MESSAGE = "No indexed papers match the selected subset."
NO_VEC_INDEX_MESSAGE = (
    "No vector index found. Run 'mosaic index' first to build the semantic search index."
)
LEGACY_INDEX_MESSAGE = (
    "The vector index uses the old per-paper format (built before full-text chunking). "
    "Run 'mosaic index --reindex' to rebuild it."
)
MIXED_INDEX_MESSAGE = (
    "Some papers are only in the old per-paper index and are ignored by retrieval. "
    "Run 'mosaic index' to add them to the current index."
)
NO_PYMUPDF_MESSAGE = (
    "full_text_index is enabled but pymupdf is not installed, so papers are indexed "
    "from metadata only. Run: pipx inject mosaic-search pymupdf"
)
_NO_VEC_MESSAGE = "sqlite-vec is not installed. Run: pipx inject mosaic-search sqlite-vec"

_DEFAULT_BATCH_SIZE = 96  # texts per embedding API call
_CONTEXT_MAX_CHARS = 24_000  # whole context block (~6k tokens)
_MIN_PAPER_CHARS = 300  # per-paper floor when many papers share the budget
_ABSTRACT_SNIPPET = 400
_HISTORY_MESSAGES = 6  # prior chat messages sent to the LLM (3 turns)

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


_WHITESPACE = re.compile(r"\s")


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

    Raises
    ------
    ValueError
        If chunk_chars <= 0 or overlap_chars is not in [0, chunk_chars).
    """
    if chunk_chars <= 0:
        raise ValueError(f"Chunk size must be positive (got {chunk_chars}).")
    if not 0 <= overlap_chars < chunk_chars:
        raise ValueError(
            f"Chunk overlap must be between 0 and the chunk size (got {overlap_chars})."
        )
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [(text, 0, len(text))]

    chunks: list[tuple[str, int, int]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_chars, n)
        # Walk back to a word boundary unless we are at the end
        if end < n:
            boundary = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start, end))
        if end >= n:
            break  # the last chunk reached the end; an overlap-only tail would be redundant
        # Advance with overlap
        next_start = end - overlap_chars
        if next_start <= start:
            next_start = end  # guard against infinite loop
        elif not text[next_start - 1].isspace():
            # Snap forward so the next chunk starts on a word, not mid-word
            match = _WHITESPACE.search(text, next_start, end)
            next_start = match.end() if match else end
        start = next_start
    return chunks


def _build_chunks(
    paper: Paper,
    cache: Cache,
    use_pdf: bool,
    chunk_chars: int,
    overlap_chars: int,
) -> tuple[list[tuple[str, int, int]], list[str], str]:
    """Return ``(chunks, embedding_inputs, text_source)`` for one paper.

    Full-text chunks are stored without the metadata header; the embedding
    input only prefixes the title so every chunk is not dominated by the
    abstract.  Metadata-only papers get a single title/authors/venue/abstract
    chunk.
    """
    from mosaic import pdf as _pdf

    source = "metadata"
    if use_pdf:
        dl = cache.get_download(paper.uid)
        if dl and dl["status"] == "ok" and dl["local_path"]:
            raw_text = _pdf.extract_text(dl["local_path"])
            raw_chunks = _chunk_text(raw_text, chunk_chars, overlap_chars) if raw_text else []
            if raw_chunks:
                prefix = f"Title: {paper.title}\n\n" if paper.title else ""
                return raw_chunks, [prefix + c_text for c_text, _, _ in raw_chunks], "pdf"
            source = "pdf_unreadable"
    meta_text = _paper_to_text(paper)
    return [(meta_text, 0, len(meta_text))], [meta_text], source


def _model_mismatch_message(stored: str, current: str) -> str:
    return (
        f"Embedding model changed: the index was built with {stored!r} but the configured "
        f"model is {current!r}. Run 'mosaic index --reindex' to rebuild the vector index."
    )


def _check_model(cache: Cache, emb_cfg: dict) -> None:
    """Raise ValueError when the index was built with a different embedding model."""
    stored = cache.get_rag_meta("embedding_model")
    current = emb_cfg.get("model", "")
    if stored and current and stored != current:
        raise ValueError(_model_mismatch_message(stored, current))


def _is_missing_table(exc: Exception) -> bool:
    return "no such table" in str(exc).lower()


def _vec_error(exc: sqlite3.OperationalError) -> Exception:
    """Translate a missing-sqlite-vec error into an actionable RuntimeError."""
    msg = str(exc).lower()
    if "no such module: vec0" in msg or "no such function: vec_" in msg:
        return RuntimeError(_NO_VEC_MESSAGE)
    return exc


def _nearest_chunk_papers(
    cache: Cache,
    query_vec: list[float],
    k: int,
    allowed: set[str] | None,
) -> list[tuple[str, str, float]] | None:
    """Nearest papers in the chunk index as ``(uid, best_chunk_id, distance)``.

    With *allowed*, the search is exact over that subset, so a narrow subset
    still gets results.  Without it, the KNN fetch grows (bounded by
    sqlite-vec's k limit) until at least *k* distinct papers are found, so one
    long PDF cannot fill the whole candidate pool.

    Returns None when the chunk index does not exist.
    """
    try:
        if allowed is not None:
            return cache.nearest_chunks_for_uids(query_vec, allowed, k)
        fetch = min(VEC_MAX_K, k * 10)
        while True:
            hits = cache.vector_search_chunks(query_vec, fetch)
            best: dict[str, tuple[str, float]] = {}  # uid -> (chunk_id, distance)
            for chunk_id, dist in hits:
                uid = chunk_id.rsplit("::", 1)[0]
                if uid not in best or dist < best[uid][1]:
                    best[uid] = (chunk_id, dist)
            if len(best) >= k or len(hits) < fetch or fetch >= VEC_MAX_K:
                break
            fetch = min(VEC_MAX_K, fetch * 4)
    except sqlite3.OperationalError as exc:
        if _is_missing_table(exc):
            return None
        raise _vec_error(exc) from exc
    ranked = sorted(best.items(), key=lambda item: item[1][1])
    return [(uid, chunk_id, dist) for uid, (chunk_id, dist) in ranked]


def _legacy_nearest(
    cache: Cache,
    query_vec: list[float],
    k: int,
    allowed: set[str] | None,
) -> list[str]:
    """Nearest papers in the legacy per-paper index ([] when it does not exist)."""
    try:
        if allowed is None:
            return cache.vector_search(query_vec, k)
        return [uid for uid, _ in cache.nearest_papers_for_uids(query_vec, allowed, k)]
    except sqlite3.OperationalError as exc:
        if _is_missing_table(exc):
            return []
        raise _vec_error(exc) from exc


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
    batch_size: int | None = None,
) -> tuple[int, int, int]:
    """
    Embed and store papers not yet in the chunk index.

    Returns ``(newly_indexed, skipped_already_indexed, full_text_count)``.
    Papers with neither title nor abstract are silently skipped.
    full_text_count is the number of papers indexed via full PDF text.

    A paper indexed from metadata only is re-indexed from its PDF once one has
    been downloaded.  Papers are stored whole: when an embedding call fails,
    papers already stored stay complete and the rest are retried next run.

    Raises ValueError on configuration problems (no model, model change,
    invalid chunk settings, old-format index) and RuntimeError when the
    embedding server fails.
    """
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    from mosaic import pdf as _pdf
    from mosaic.config import _DEFAULTS, get_embedding_cfg
    from mosaic.embeddings import embed_texts

    emb_cfg = get_embedding_cfg(cfg)
    model = emb_cfg.get("model", "")
    if not model:
        raise ValueError(
            "No embedding model configured. Run: mosaic config --embedding-model <model-name>"
        )

    rag_cfg = cfg.get("rag", {})
    chunk_size = int(rag_cfg.get("chunk_size", _DEFAULTS["rag"]["chunk_size"]))
    chunk_overlap = int(rag_cfg.get("chunk_overlap", _DEFAULTS["rag"]["chunk_overlap"]))
    if chunk_size <= 0:
        raise ValueError(f"rag.chunk_size must be a positive number of tokens (got {chunk_size}).")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError(
            f"rag.chunk_overlap must be between 0 and rag.chunk_size - 1 "
            f"(got {chunk_overlap} with chunk_size {chunk_size})."
        )
    chunk_chars = chunk_size * 4
    overlap_chars = chunk_overlap * 4
    full_text_enabled = rag_cfg.get("full_text_index", True)
    batch_size = int(batch_size or _DEFAULT_BATCH_SIZE)
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1 (got {batch_size}).")

    # Detect model change
    stored_model = cache.get_rag_meta("embedding_model")
    if stored_model and stored_model != model and not reindex:
        raise ValueError(
            f"Embedding model changed: stored={stored_model!r}, current={model!r}. "
            "Run 'mosaic index --reindex' to rebuild the vector index."
        )
    if reindex:
        cache.rebuild_vec_table()
    elif cache.has_legacy_only_index():
        # Adding chunks now would make retrieval ignore every legacy-indexed paper.
        raise ValueError(LEGACY_INDEX_MESSAGE)

    use_pdf = bool(full_text_enabled) and _pdf.is_available()
    if full_text_enabled and not use_pdf:
        _log.warning(NO_PYMUPDF_MESSAGE)

    already_indexed = cache.get_indexed_uids()
    upgradable: set[str] = set()
    if use_pdf and already_indexed and not reindex:
        upgradable = cache.get_metadata_only_uids() & cache.get_downloaded_uids()

    # Filter candidates (each uid once)
    candidates: list[Paper] = []
    seen: set[str] = set()
    for p in papers:
        if p.uid in seen or not (p.title or p.abstract):
            continue
        seen.add(p.uid)
        if reindex or p.uid not in already_indexed or p.uid in upgradable:
            candidates.append(p)
    skipped = len(papers) - len(candidates)

    if not candidates:
        return 0, skipped, 0

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

    newly_indexed = 0
    full_text_count = 0
    model_recorded = False
    # Papers waiting to be embedded: (paper, chunks, embedding inputs, text source)
    pending: list[tuple[Paper, list[tuple[str, int, int]], list[str], str]] = []

    def _flush() -> None:
        nonlocal newly_indexed, full_text_count, model_recorded
        texts = [text for _, _, inputs, _ in pending for text in inputs]
        embeddings = embed_texts(texts, emb_cfg, batch_size=batch_size)
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"The embedding server returned {len(embeddings)} vectors for {len(texts)} texts."
            )
        vectors = iter(embeddings)
        rows: list[tuple] = []
        sources: dict[str, str] = {}
        for paper, chunks, _, source in pending:
            sources[paper.uid] = source
            for idx, (chunk_text, char_start, char_end) in enumerate(chunks):
                chunk_id = f"{paper.uid}::{idx}"
                rows.append(
                    (chunk_id, paper.uid, idx, chunk_text, char_start, char_end, next(vectors))
                )
        if not model_recorded:
            # Persist model name for future consistency checks
            cache.set_rag_meta("embedding_model", model)
            model_recorded = True
        try:
            cache.upsert_chunks_batch(rows, len(embeddings[0]), text_sources=sources)
        except sqlite3.OperationalError as exc:
            if "dimension mismatch" in str(exc).lower():
                raise ValueError(
                    f"The embedding model returns vectors of a different size than the "
                    f"existing index ({exc}). Run 'mosaic index --reindex' to rebuild it."
                ) from exc
            raise
        newly_indexed += len(pending)
        full_text_count += sum(1 for *_, source in pending if source == "pdf")
        if prog and task is not None:
            prog.advance(task, len(pending))
        pending.clear()

    try:
        pending_chunks = 0
        for paper in candidates:
            chunks, inputs, source = _build_chunks(
                paper, cache, use_pdf, chunk_chars, overlap_chars
            )
            pending.append((paper, chunks, inputs, source))
            pending_chunks += len(chunks)
            if pending_chunks >= batch_size:
                _flush()
                pending_chunks = 0
        if pending:
            _flush()
    finally:
        if prog:
            prog.stop()

    cache.drop_legacy_index_if_superseded()
    return newly_indexed, skipped, full_text_count


def index_health(cfg: dict, cache: Cache) -> list[str]:
    """Return user-facing problems with the vector index, for the CLI / web UI to show.

    Covers conditions that are otherwise only logged: missing sqlite-vec or
    pymupdf, an old-format or mixed index, and an embedding model change.
    """
    from mosaic import pdf as _pdf
    from mosaic.config import get_embedding_cfg

    warnings: list[str] = []
    tables = cache.vec_tables()
    if tables and not cache.vec_available:
        warnings.append(f"The vector index cannot be used: {_NO_VEC_MESSAGE}")
    if cache.has_legacy_only_index():
        warnings.append(LEGACY_INDEX_MESSAGE)
    elif {"vec_papers", "vec_chunks"} <= tables:
        warnings.append(MIXED_INDEX_MESSAGE)
    stored = cache.get_rag_meta("embedding_model")
    current = get_embedding_cfg(cfg).get("model", "")
    if stored and current and stored != current:
        warnings.append(_model_mismatch_message(stored, current))
    if cfg.get("rag", {}).get("full_text_index", True) and not _pdf.is_available():
        warnings.append(NO_PYMUPDF_MESSAGE)
    return warnings


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
    """Embed query, de-duplicate chunks to paper level, return papers + best chunk texts.

    *pre_filter* restricts retrieval to those UIDs; an empty list matches
    nothing.  Only full-text chunks are returned in the chunk-text map;
    metadata-only papers are represented by their abstract.
    """
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
    rag_cfg = cfg.get("rag", {})
    top_k = max(1, int(k or rag_cfg.get("top_k", 10)))

    allowed = set(pre_filter) if pre_filter is not None else None
    if allowed is not None and not allowed:
        return [], {}
    _check_model(cache, emb_cfg)

    query_embeddings = embed_texts([query], emb_cfg)
    if not query_embeddings:
        return [], {}
    query_vec = query_embeddings[0]

    citations_cfg = rag_cfg.get("citations", {}) or {}
    boost = bool(citations_cfg.get("enabled", False))
    n_candidates = top_k * 3 if boost else top_k

    # Chunk index first (current format), legacy per-paper index as fallback
    best_chunk: dict[str, str] = {}
    hits = _nearest_chunk_papers(cache, query_vec, n_candidates, allowed)
    if hits:
        uids = [uid for uid, _, _ in hits]
        best_chunk = {uid: chunk_id for uid, chunk_id, _ in hits}
    else:
        uids = _legacy_nearest(cache, query_vec, n_candidates, allowed)
        if hits is None and uids:
            _log.warning(LEGACY_INDEX_MESSAGE)

    # Citation boosting
    if boost and uids:
        alpha = float(citations_cfg.get("boost_alpha", 0.3))
        uids = _citation_boost(uids, cache, alpha, top_k)
    uids = uids[:top_k]
    if boost and citations_cfg.get("expand_neighbors", False) and uids:
        uids = _with_neighbors(uids, cache, top_k, allowed)

    # Fetch papers and best chunk texts
    papers = cache.get_papers_by_uids(uids)
    uid_order = {uid: i for i, uid in enumerate(uids)}
    papers.sort(key=lambda p: uid_order.get(p.uid, 9999))

    best_chunk_ids = [best_chunk[uid] for uid in uids if uid in best_chunk]
    chunk_texts = (
        cache.get_chunk_texts(best_chunk_ids, full_text_only=True) if best_chunk_ids else {}
    )
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
    ``1 / (1 + L2_distance)``, mapping distance to a (0, 1] similarity value,
    using each paper's best-matching chunk.

    Raises RuntimeError if sqlite-vec is not installed or no vector index
    exists, or ValueError if no embedding model is configured or the index
    was built with a different model.
    """
    from mosaic.config import get_embedding_cfg
    from mosaic.embeddings import embed_texts

    emb_cfg = get_embedding_cfg(cfg)
    _check_model(cache, emb_cfg)
    vecs = embed_texts([query], emb_cfg)
    if not vecs:
        return []
    query_vec = vecs[0]
    k = max(1, int(k))

    allowed = cache.get_downloaded_uids() if downloaded_only else None
    if allowed is not None and not allowed:
        return []

    hits = _nearest_chunk_papers(cache, query_vec, k, allowed)
    if hits:
        scored = [(uid, dist) for uid, _, dist in hits][:k]
    else:
        try:
            if allowed is None:
                scored = cache.vector_search_scored(query_vec, k)
            else:
                scored = cache.nearest_papers_for_uids(query_vec, allowed, k)
        except sqlite3.OperationalError as exc:
            if not _is_missing_table(exc):
                raise _vec_error(exc) from exc
            if hits is None:
                raise RuntimeError(NO_VEC_INDEX_MESSAGE) from exc
            scored = []

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

    Returns ``(answer_text, retrieved_papers)``.  When nothing is retrieved
    the answer is ``NO_INDEX_MESSAGE`` (or ``NO_SUBSET_MESSAGE`` when a
    *pre_filter* was given) and the paper list is empty.
    """
    return _answer(query, [], cfg, cache, mode=mode, k=k, pre_filter=pre_filter)


def chat_turn(
    question: str,
    history: list[dict],
    cfg: dict,
    cache: Cache,
    *,
    mode: str = "synthesis",
    k: int | None = None,
    pre_filter: list[str] | None = None,
) -> tuple[str, list[Paper]]:
    """One conversational RAG turn.

    Retrieves context for *question* like ``ask()``, then sends the last
    prior turns of *history* (``{"role": "user"|"assistant", "content": str}``
    dicts, oldest first, answered turns only) followed by the context prompt.
    Returns ``(answer_text, retrieved_papers)`` with the same empty-result
    messages as ``ask()``; the caller appends the new turn to its history.
    """
    return _answer(question, history, cfg, cache, mode=mode, k=k, pre_filter=pre_filter)


def _answer(
    question: str,
    history: list[dict],
    cfg: dict,
    cache: Cache,
    *,
    mode: str,
    k: int | None,
    pre_filter: list[str] | None,
) -> tuple[str, list[Paper]]:
    if pre_filter is not None and not pre_filter:
        return NO_SUBSET_MESSAGE, []
    papers, chunk_texts = retrieve_with_context(question, cfg, cache, k=k, pre_filter=pre_filter)
    if not papers:
        return (NO_SUBSET_MESSAGE if pre_filter is not None else NO_INDEX_MESSAGE), []

    context = _build_context(papers, chunk_texts)
    template = _PROMPTS.get(mode, _PROMPTS["synthesis"])
    prompt = template.format(query=question, context=context)

    prior = _history_messages(history)
    answer = _call_llm([*prior, {"role": "user", "content": prompt}] if prior else prompt, cfg)
    return answer, papers


def _history_messages(history: list[dict] | None) -> list[dict]:
    """Normalise chat history into alternating user/assistant messages.

    Keeps the last ``_HISTORY_MESSAGES`` messages, merges consecutive
    same-role entries, and trims so the list starts with a user message and
    ends with an assistant one (the new question is appended by the caller).
    """
    messages: list[dict] = []
    for msg in history or []:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1] = {"role": role, "content": f"{messages[-1]['content']}\n\n{content}"}
        else:
            messages.append({"role": role, "content": content})
    messages = messages[-_HISTORY_MESSAGES:]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    while messages and messages[-1]["role"] != "assistant":
        messages.pop()
    return messages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_context(
    papers: list[Paper],
    chunk_texts: dict[str, str] | None = None,
) -> str:
    """Build numbered context block for the LLM prompt.

    Each paper gets a header line plus either its abstract snippet and best
    full-text excerpt, or the abstract alone.  Bodies share a total budget of
    ``_CONTEXT_MAX_CHARS`` so large *k* values cannot overflow the model context.
    """
    excerpts: dict[str, str] = {}
    for chunk_id, text in (chunk_texts or {}).items():
        excerpts.setdefault(chunk_id.rsplit("::", 1)[0], text)
    budget = max(_MIN_PAPER_CHARS, _CONTEXT_MAX_CHARS // max(len(papers), 1))

    parts = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:5]) if p.authors else "Unknown"
        if len(p.authors) > 5:
            authors += " et al."
        header = f"[{i}] {p.title or 'Untitled'} — {authors} ({p.year or '?'})"
        if p.journal:
            header += f", {p.journal}"

        # Use best-matching full-text excerpt if available, else the abstract
        abstract = (p.abstract or "")[:_ABSTRACT_SNIPPET]
        excerpt = excerpts.get(p.uid, "")
        if excerpt:
            body = (
                f"Abstract: {abstract}\nExcerpt: {excerpt}" if abstract else f"Excerpt: {excerpt}"
            )
        else:
            body = abstract or "(no abstract)"
        if len(body) > budget:
            body = body[:budget].rstrip() + "…"

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


def _with_neighbors(
    uids: list[str],
    cache: Cache,
    top_k: int,
    allowed: set[str] | None,
) -> list[str]:
    """Give citation neighbors of the top results a share of the *top_k* slots.

    Neighbors fill any free slots and are guaranteed at least ``top_k // 5``
    (minimum 1) slots, replacing the lowest-ranked similarity hits; the best
    similarity hit is always kept.  Neighbors outside *allowed* are ignored.
    """
    head = list(uids)
    extra = [
        n
        for n in _expand_neighbors(head, cache, top_k)[len(head) :]
        if allowed is None or n in allowed
    ]
    if not extra:
        return head
    free = max(top_k - len(head), 0)
    n_add = min(len(extra), max(free, max(1, top_k // 5)))
    keep = min(len(head), max(1, top_k - n_add))
    n_add = min(n_add, top_k - keep)
    return head[:keep] + extra[:n_add]


def _response_detail(resp: httpx.Response) -> str:
    """Short error detail from an HTTP error response body (for messages)."""
    try:
        data = resp.json()
        err = data.get("error", data) if isinstance(data, dict) else data
        detail = err.get("message", "") if isinstance(err, dict) else str(err)
    except Exception:
        detail = resp.text or ""
    detail = " ".join(str(detail).split())[:200]
    return f": {detail}" if detail else ""


def _post_llm(url: str, headers: dict, payload: dict) -> dict:
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"LLM request failed: HTTP {exc.response.status_code} from {url}"
            f"{_response_detail(exc.response)}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"LLM request failed: could not reach {url} ({type(exc).__name__})."
        ) from exc
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(f"LLM returned a non-JSON response from {url}.") from exc


def _call_llm(prompt: str | list[dict], cfg: dict, *, max_tokens: int = 4096) -> str:
    """Call the configured LLM generator and return the response text.

    *prompt* is either a single user message or a full ``messages`` list
    (alternating user/assistant, ending with user).  Raises ValueError when
    no LLM is configured and RuntimeError when the request fails.
    """
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

    messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else list(prompt)

    if provider == "openai" or base_url:
        url = (
            f"{base_url}/chat/completions"
            if base_url
            else "https://api.openai.com/v1/chat/completions"
        )
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload: dict = {"model": model, "messages": messages}
        data = _post_llm(url, headers, payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"LLM returned an unexpected response from {url}.") from exc

    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "max_tokens": max_tokens, "messages": messages}
        data = _post_llm(url, headers, payload)
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"LLM returned an unexpected response from {url}.") from exc

    raise ValueError(f"Unknown LLM provider: {provider!r}")
