"""Embedding client for the RAG pipeline."""

from __future__ import annotations

import logging

import httpx

from mosaic.errors import MosaicError
from mosaic.llm import openai_url

_log = logging.getLogger(__name__)

_BATCH_SIZE = 96


class EmbeddingError(MosaicError, ValueError):
    """Raised when the embedding server cannot be reached or answers with an error.

    Also a ValueError, so the commands that report configuration problems report it too.
    """


def embed_texts(
    texts: list[str], emb_cfg: dict, batch_size: int = _BATCH_SIZE
) -> list[list[float]]:
    """
    Embed *texts* using the configured embedding model.

    *emb_cfg* is the resolved dict from ``config.get_embedding_cfg(cfg)``.
    Uses the OpenAI-compatible ``/v1/embeddings`` endpoint, which is supported
    by cloud OpenAI, Ollama, LM Studio, LocalAI, and most other local servers.

    Returns a list of float vectors, one per input text, in the same order.
    """
    if not texts:
        return []

    model = emb_cfg.get("model", "")
    api_key = emb_cfg.get("api_key", "") or "placeholder"
    base_url = emb_cfg.get("base_url", "").rstrip("/")

    if not model:
        raise ValueError(
            "No embedding model configured. Run: mosaic config --embedding-model <model-name>"
        )

    url = openai_url(base_url, "embeddings") if base_url else "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        payload = {"model": model, "input": batch}
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=120)
        except httpx.HTTPError as e:
            raise EmbeddingError(f"Could not reach the embedding server at {url}: {e}") from e
        if resp.is_error:
            raise EmbeddingError(
                f"{url} returned HTTP {resp.status_code}: {_error_detail(resp)}"
                + (" (is the model pulled?)" if resp.status_code == 404 else "")
            )
        data = resp.json()
        # OpenAI response: {"data": [{"index": 0, "embedding": [...]}, ...]}
        items = sorted(data["data"], key=lambda x: x["index"])
        all_embeddings.extend(item["embedding"] for item in items)

    return all_embeddings


def _error_detail(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error")
        return err.get("message", "") if isinstance(err, dict) else str(err or resp.reason_phrase)
    except Exception:
        return resp.text[:200] or resp.reason_phrase
