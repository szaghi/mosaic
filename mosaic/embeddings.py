"""Embedding client for the RAG pipeline."""

from __future__ import annotations

import logging

import httpx

_log = logging.getLogger(__name__)

_BATCH_SIZE = 96


def embed_texts(texts: list[str], emb_cfg: dict) -> list[list[float]]:
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

    url = f"{base_url}/v1/embeddings" if base_url else "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        payload = {"model": model, "input": batch}
        resp = httpx.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        # OpenAI response: {"data": [{"index": 0, "embedding": [...]}, ...]}
        items = sorted(data["data"], key=lambda x: x["index"])
        all_embeddings.extend(item["embedding"] for item in items)

    return all_embeddings
