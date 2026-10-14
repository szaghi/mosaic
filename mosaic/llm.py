"""Single entry point for chat-completion calls to the configured LLM.

Supports cloud OpenAI, Anthropic, and any OpenAI-compatible server reached via
``llm.base_url`` (Ollama, LM Studio, llama.cpp, LocalAI, ...). Configuration lives
under the ``[llm]`` section: ``provider``, ``api_key``, ``model``, ``base_url``.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from mosaic.errors import ConfigError, MosaicError

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"

NOT_CONFIGURED_HINT = "No LLM configured. Run: mosaic config --llm-provider openai --llm-api-key KEY --llm-model MODEL"


class LLMConfigError(ConfigError, ValueError):
    """Raised when the ``[llm]`` section is missing or names an unknown provider.

    Also a ValueError so existing ``except ValueError`` handlers keep working.
    """


class LLMRequestError(MosaicError):
    """Raised when the LLM server answers with an HTTP error.

    The message carries the server's own explanation (e.g. Ollama's
    "model 'x' not found"), which a bare HTTPStatusError hides.
    """


def _raise_for_status(resp: httpx.Response, s: LLMSettings) -> None:
    if not resp.is_error:
        return
    detail = ""
    try:
        err = resp.json().get("error")
        detail = err.get("message", "") if isinstance(err, dict) else str(err or "")
    except Exception:
        detail = resp.text[:300]
    where = s.base_url or s.provider
    raise LLMRequestError(
        f"{where} returned HTTP {resp.status_code}: {detail or resp.reason_phrase}"
    )


@dataclass(frozen=True)
class LLMSettings:
    """Resolved ``[llm]`` configuration."""

    provider: str
    api_key: str
    model: str
    base_url: str

    @property
    def openai_compatible(self) -> bool:
        """True for cloud OpenAI and for any custom ``base_url`` server."""
        return self.provider == "openai" or bool(self.base_url)


def is_configured(cfg: dict) -> bool:
    """Return True if *cfg* has both an LLM provider and an API key."""
    llm_cfg = cfg.get("llm", {})
    return bool(llm_cfg.get("provider") and llm_cfg.get("api_key"))


def resolve(cfg: dict) -> LLMSettings:
    """Resolve the ``[llm]`` section of *cfg*, filling in the default model.

    Raises
    ------
    LLMConfigError
        If provider or API key is missing, or the provider is unknown.
    """
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "").lower()
    api_key = llm_cfg.get("api_key", "")
    base_url = llm_cfg.get("base_url", "").rstrip("/")
    if not provider or not api_key:
        raise LLMConfigError(NOT_CONFIGURED_HINT)
    if provider not in DEFAULT_MODELS and not base_url:
        raise LLMConfigError(f"Unknown LLM provider: {provider!r}")
    model = llm_cfg.get("model", "") or DEFAULT_MODELS.get(provider, "")
    return LLMSettings(provider, api_key, model, base_url)


def complete(
    prompt: str | list[dict[str, str]],
    cfg: dict,
    *,
    max_tokens: int = 4096,
    json_mode: bool = False,
    timeout: float = 180,
) -> str:
    """Send *prompt* to the configured LLM and return the response text.

    Parameters
    ----------
    prompt : str or list of dict
        A single user prompt, or a full ``[{"role": ..., "content": ...}]``
        message list (for multi-turn chat).
    cfg : dict
        Full MOSAIC config; only the ``[llm]`` section is read.
    max_tokens : int
        Response cap. Sent to Anthropic, which requires it; OpenAI-compatible
        servers use their own default.
    json_mode : bool
        Request a JSON response. Honoured only by cloud OpenAI: many local
        servers reject ``response_format``, and Anthropic has no equivalent.
    timeout : float
        HTTP timeout in seconds.

    Returns
    -------
    str
        The assistant message text.

    Raises
    ------
    LLMConfigError
        If the LLM is not configured.
    LLMRequestError
        If the server answers with an HTTP error (message includes its reason).
    httpx.HTTPError
        On transport errors (connection refused, timeout).
    """
    s = resolve(cfg)
    messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt

    if s.openai_compatible:
        url = f"{s.base_url}/chat/completions" if s.base_url else _OPENAI_URL
        headers = {"Authorization": f"Bearer {s.api_key}", "Content-Type": "application/json"}
        payload: dict = {"model": s.model, "messages": messages}
        if json_mode and not s.base_url:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        _raise_for_status(resp, s)
        return resp.json()["choices"][0]["message"]["content"]

    headers = {
        "x-api-key": s.api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    payload = {"model": s.model, "max_tokens": max_tokens, "messages": messages}
    resp = httpx.post(_ANTHROPIC_URL, headers=headers, json=payload, timeout=timeout)
    _raise_for_status(resp, s)
    return resp.json()["content"][0]["text"]
