"""Embedding client for the RAG pipeline."""

from __future__ import annotations

import logging
import re

import httpx

_log = logging.getLogger(__name__)

_BATCH_SIZE = 96

_VERSION_SUFFIX = re.compile(r"/v\d+$")


def embeddings_url(base_url: str) -> str:
    """Return the ``/embeddings`` endpoint for an OpenAI-compatible *base_url*.

    Accepts the documented form that already ends in a version segment
    (``http://localhost:11434/v1``), a bare host (``http://localhost:11434``,
    ``/v1`` is added) or the full endpoint.  Empty means the OpenAI cloud.
    """
    base = (base_url or "").rstrip("/")
    if not base:
        return "https://api.openai.com/v1/embeddings"
    if base.endswith("/embeddings"):
        return base
    if _VERSION_SUFFIX.search(base):
        return f"{base}/embeddings"
    return f"{base}/v1/embeddings"


def embed_texts(
    texts: list[str],
    emb_cfg: dict,
    *,
    batch_size: int | None = None,
) -> list[list[float]]:
    """
    Embed *texts* using the configured embedding model.

    *emb_cfg* is the resolved dict from ``config.get_embedding_cfg(cfg)``.
    Uses the OpenAI-compatible ``/v1/embeddings`` endpoint, which is supported
    by cloud OpenAI, Ollama, LM Studio, LocalAI, and most other local servers.
    *batch_size* is the number of texts per API call (default 96).

    Returns a list of float vectors, one per input text, in the same order.
    Raises ValueError when no model is configured and RuntimeError when the
    embedding server cannot be reached or rejects the request.
    """
    if not texts:
        return []

    model = emb_cfg.get("model", "")
    api_key = emb_cfg.get("api_key", "") or "placeholder"

    if not model:
        raise ValueError(
            "No embedding model configured. Run: mosaic config --embedding-model <model-name>"
        )

    url = embeddings_url(emb_cfg.get("base_url", ""))
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    size = max(1, int(batch_size or _BATCH_SIZE))

    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), size):
        batch = texts[i : i + size]
        payload = {"model": model, "input": batch}
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Embedding request failed: HTTP {exc.response.status_code} from {url}. "
                "Check rag.embedding_base_url (e.g. http://localhost:11434/v1) "
                "and rag.embedding_model."
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Embedding request failed: could not reach {url} ({type(exc).__name__})."
            ) from exc
        data = resp.json()
        # OpenAI response: {"data": [{"index": 0, "embedding": [...]}, ...]}
        items = sorted(data["data"], key=lambda x: x["index"])
        all_embeddings.extend(item["embedding"] for item in items)

    return all_embeddings
