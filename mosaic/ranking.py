"""Relevance scoring for search results."""

from __future__ import annotations

import json
import logging

import httpx

from mosaic.models import Paper

_log = logging.getLogger(__name__)


def score_papers(query: str, papers: list[Paper], cfg: dict) -> list[Paper]:
    """Score *papers* by relevance to *query*, setting ``relevance_score`` in place.

    Uses BM25 by default.  If ``cfg["llm"]["api_key"]`` and ``cfg["llm"]["provider"]``
    are set, the LLM scorer is tried first and BM25 is used as a fallback.
    """
    if not papers or not query.strip():
        return papers
    llm_cfg = cfg.get("llm", {})
    if llm_cfg.get("api_key") and llm_cfg.get("provider"):
        try:
            return _llm_score(query, papers, llm_cfg)
        except Exception as exc:
            _log.warning("LLM scoring failed (%s) — falling back to BM25", exc)
    return _bm25_score(query, papers)


# ---------------------------------------------------------------------------
# BM25 scorer
# ---------------------------------------------------------------------------


def _bm25_score(query: str, papers: list[Paper]) -> list[Paper]:
    # BM25Plus uses log((N+1)/freq) for IDF, which is always positive and avoids the
    # zero-IDF issue of BM25Okapi when a term appears in exactly half the corpus.
    from rank_bm25 import BM25Plus

    corpus = [(p.title or "") + " " + (p.abstract or "") for p in papers]
    tokenised = [doc.lower().split() for doc in corpus]
    bm25 = BM25Plus(tokenised)
    scores = bm25.get_scores(query.lower().split())
    max_s = float(scores.max()) if scores.max() > 0 else 1.0
    for paper, s in zip(papers, scores, strict=True):
        paper.relevance_score = round(max(float(s) / max_s, 0.0), 4)
    return papers


# ---------------------------------------------------------------------------
# LLM scorer (opt-in)
# ---------------------------------------------------------------------------


def _llm_score(query: str, papers: list[Paper], llm_cfg: dict) -> list[Paper]:
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    provider = llm_cfg.get("provider", "").lower()
    api_key = llm_cfg["api_key"]
    model = llm_cfg.get("model") or _default_model(provider)
    base_url = llm_cfg.get("base_url", "").rstrip("/")
    batch_size = 20

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Scoring relevance[/cyan] [dim]({model})[/dim]",
            total=len(papers),
        )
        for i in range(0, len(papers), batch_size):
            batch = papers[i : i + batch_size]
            snippets = "\n".join(
                f"{j + 1}. {p.title}: {(p.abstract or '')[:300]}" for j, p in enumerate(batch)
            )
            prompt = (
                f"Query: {query!r}\n\n"
                f"Rate the relevance of each paper to the query on a scale 0.0–1.0.\n"
                f"Return a JSON array of exactly {len(batch)} floats, one per paper, in order.\n\n"
                f"{snippets}"
            )
            raw_scores = _call_llm(
                provider, api_key, model, prompt, expected=len(batch), base_url=base_url
            )
            for paper, s in zip(batch, raw_scores, strict=True):
                paper.relevance_score = round(float(s), 4)
            progress.advance(task, len(batch))

    return papers


def _call_llm(
    provider: str, api_key: str, model: str, prompt: str, expected: int, base_url: str = ""
) -> list[float]:
    if provider == "openai" or base_url:
        # OpenAI-compatible endpoint — used for cloud OpenAI and any local server
        # (Ollama, LM Studio, llama.cpp, LocalAI, etc.)
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
        # JSON-mode is supported by cloud OpenAI and most local servers that
        # understand the spec; omit it when using a custom base_url to stay
        # compatible with servers that don't implement response_format yet.
        if not base_url:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = httpx.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
    else:
        raise ValueError(f"Unknown LLM provider: {provider!r}")

    scores = _parse_float_list(content, expected)
    return scores


def _parse_float_list(content: str, expected: int) -> list[float]:
    """Extract a list of *expected* floats from an LLM JSON response."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON: {content[:200]!r}") from exc

    if isinstance(data, list):
        floats = [float(x) for x in data[:expected]]
    elif isinstance(data, dict):
        # Some models wrap: {"scores": [...]} or {"relevance": [...]}
        floats = None
        for v in data.values():
            if isinstance(v, list):
                floats = [float(x) for x in v[:expected]]
                break
        if floats is None:
            raise ValueError(f"No list found in LLM response dict: {list(data.keys())}")
    else:
        raise ValueError(f"Unexpected LLM response type: {type(data).__name__}")

    # Pad to expected length with neutral score if model returned fewer items
    while len(floats) < expected:
        floats.append(0.5)
    return floats[:expected]


def _default_model(provider: str) -> str:
    if provider == "openai":
        return "gpt-4o-mini"
    if provider == "anthropic":
        return "claude-haiku-4-5-20251001"
    return ""
