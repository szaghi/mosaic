"""Configuration management (~/.config/mosaic/config.toml)."""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

import tomli_w

from mosaic.errors import ConfigError  # noqa: F401 — available for future use

_log = logging.getLogger(__name__)

_CONFIG_PATH = Path.home() / ".config" / "mosaic" / "config.toml"

_DEFAULTS: dict = {
    "download_dir": str(Path.home() / "mosaic-papers"),
    "db_path": str(Path.home() / ".local" / "share" / "mosaic" / "cache.db"),
    "rate_limit_delay": 1.0,
    "filename_pattern": "{year}_{source}_{author}_{title}",
    "sources": {
        "arxiv": {"enabled": True},
        "semantic_scholar": {"enabled": True, "api_key": ""},
        "sciencedirect": {"enabled": True, "api_key": ""},
        "doaj": {"enabled": True},
        "europepmc": {"enabled": True},
        "openalex": {"enabled": True},
        "base": {"enabled": True},
        "springer_api": {"enabled": True, "api_key": ""},
        "core": {"enabled": True, "api_key": ""},
        "nasa_ads": {"enabled": True, "api_key": ""},
        "ieee": {"enabled": True, "api_key": ""},
        "zenodo": {"enabled": True, "api_key": ""},
        "crossref": {"enabled": True},
        "dblp": {"enabled": True},
        "hal": {"enabled": True},
        "pubmed": {"enabled": True, "api_key": ""},
        "pmc": {"enabled": True, "api_key": ""},
        "biorxiv": {"enabled": True},
        "pedro": {
            "enabled": True,
            "acknowledge_fair_use": False,
            "rate_limit_delay": 3.0,
            "fetch_details": False,
        },
        "scopus": {"enabled": True, "api_key": "", "inst_token": ""},
    },
    "unpaywall": {"email": ""},
    "zotero": {"api_key": "", "user_id": 0},
    "obsidian": {
        "vault_path": "",
        "subfolder": "papers",
        "filename_pattern": "{year}_{author}_{title}",
        "tags": ["paper"],
        "wikilinks": True,
    },
    "custom_sources": [],
    "llm": {"provider": "", "api_key": "", "model": "", "base_url": ""},
    "rag": {
        "embedding_provider": "",  # "openai" or leave empty (inherits llm.provider)
        "embedding_model": "",  # e.g. "snowflake-arctic-embed2", "text-embedding-3-small"
        "embedding_base_url": "",  # e.g. "http://localhost:11434/v1" for Ollama
        "embedding_api_key": "",  # leave empty to inherit llm.api_key
        "top_k": 10,  # papers retrieved per query
        "chunk_size": 512,  # max characters per text chunk (reserved for future full-PDF mode)
        "auto_index": False,  # silently index new papers after each search/get
        "citations": {
            "enabled": False,  # apply citation graph boosting in retrieve()
            "boost_alpha": 0.3,  # re-scoring weight; 0 = pure cosine, >0 = citation boost
            "providers": ["openalex", "crossref"],  # priority order
            "expand_neighbors": False,  # widen recall by adding 1-hop citation neighbors
        },
    },
}


_KNOWN_SOURCES: set[str] = {
    "arxiv",
    "semantic_scholar",
    "sciencedirect",
    "doaj",
    "europepmc",
    "openalex",
    "base",
    "springer_api",
    "core",
    "nasa_ads",
    "ieee",
    "zenodo",
    "crossref",
    "dblp",
    "hal",
    "pubmed",
    "pmc",
    "biorxiv",
    "pedro",
    "springer",
    "scopus",
}


def validate(cfg: dict) -> list[str]:
    """Validate a loaded config dict and return a list of warning messages."""
    warnings: list[str] = []

    # -- top-level scalars ---------------------------------------------------
    if "download_dir" in cfg and not isinstance(cfg["download_dir"], str):
        warnings.append("download_dir should be a string")

    if "rate_limit_delay" in cfg:
        rld = cfg["rate_limit_delay"]
        if not isinstance(rld, (int, float)):
            warnings.append("rate_limit_delay should be a number")
        elif rld < 0:
            warnings.append("rate_limit_delay should be >= 0")

    if "filename_pattern" in cfg and not isinstance(cfg["filename_pattern"], str):
        warnings.append("filename_pattern should be a string")

    # -- sources -------------------------------------------------------------
    sources = cfg.get("sources")
    if isinstance(sources, dict):
        for name, src_cfg in sources.items():
            if name not in _KNOWN_SOURCES:
                warnings.append(f"unknown source '{name}'")
            if isinstance(src_cfg, dict):
                if "enabled" in src_cfg and not isinstance(src_cfg["enabled"], bool):
                    warnings.append(f"sources.{name}.enabled should be a bool")
                if "api_key" in src_cfg and not isinstance(src_cfg["api_key"], str):
                    warnings.append(f"sources.{name}.api_key should be a string")

    # -- unpaywall -----------------------------------------------------------
    unpaywall = cfg.get("unpaywall")
    if isinstance(unpaywall, dict):
        email = unpaywall.get("email")
        if email is not None and email != "" and not isinstance(email, str):
            warnings.append("unpaywall.email should be a string")

    # -- zotero --------------------------------------------------------------
    zotero = cfg.get("zotero")
    if isinstance(zotero, dict):
        if "api_key" in zotero and not isinstance(zotero["api_key"], str):
            warnings.append("zotero.api_key should be a string")
        if "user_id" in zotero and not isinstance(zotero["user_id"], int):
            warnings.append("zotero.user_id should be an int")

    # -- obsidian ------------------------------------------------------------
    obsidian = cfg.get("obsidian")
    if isinstance(obsidian, dict):
        if "vault_path" in obsidian and not isinstance(obsidian["vault_path"], str):
            warnings.append("obsidian.vault_path should be a string")
        if "tags" in obsidian and not isinstance(obsidian["tags"], list):
            warnings.append("obsidian.tags should be a list")
        if "wikilinks" in obsidian and not isinstance(obsidian["wikilinks"], bool):
            warnings.append("obsidian.wikilinks should be a bool")

    return warnings


def load() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        # merge missing keys from defaults
        cfg = _merge(_DEFAULTS, data)
    else:
        cfg = dict(_DEFAULTS)

    for msg in validate(cfg):
        _log.warning("config: %s", msg)

    return cfg


def save(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 0o600: config contains API keys — restrict to owner only, set atomically
    raw_fd = os.open(str(_CONFIG_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(raw_fd, "wb") as f:
        tomli_w.dump(cfg, f)


# ---------------------------------------------------------------------------
# Shared API-key registry — used by both CLI and web UI config forms.
# Each tuple is (input_key_name, config_path_tuple).
# ---------------------------------------------------------------------------

API_KEY_PATHS: list[tuple[str, tuple[str, ...]]] = [
    ("elsevier_key", ("sources", "sciencedirect", "api_key")),
    ("ss_key", ("sources", "semantic_scholar", "api_key")),
    ("core_key", ("sources", "core", "api_key")),
    ("ads_key", ("sources", "nasa_ads", "api_key")),
    ("ieee_key", ("sources", "ieee", "api_key")),
    ("ncbi_key", ("sources", "pubmed", "api_key")),
    ("springer_key", ("sources", "springer_api", "api_key")),
    ("scopus_key", ("sources", "scopus", "api_key")),
    ("scopus_inst_token", ("sources", "scopus", "inst_token")),
    ("zenodo_key", ("sources", "zenodo", "api_key")),
]


def apply_api_keys(cfg: dict, updates: dict[str, str]) -> bool:
    """Apply API key updates to *cfg* using ``API_KEY_PATHS``.

    Args:
        cfg: The config dict to update in place.
        updates: Mapping of input key names to values (empty strings are skipped).

    Returns:
        True if any key was actually set.
    """
    changed = False
    for key_name, cfg_path in API_KEY_PATHS:
        val = updates.get(key_name, "").strip()
        if not val:
            continue
        d = cfg
        for part in cfg_path[:-1]:
            d = d.setdefault(part, {})
        d[cfg_path[-1]] = val
        changed = True
    return changed


def get_embedding_cfg(cfg: dict) -> dict:
    """Return resolved embedding config, falling back to [llm] values where unset."""
    rag = cfg.get("rag", {})
    llm = cfg.get("llm", {})
    return {
        "provider": rag.get("embedding_provider") or llm.get("provider", ""),
        "model": rag.get("embedding_model", ""),
        "base_url": rag.get("embedding_base_url") or llm.get("base_url", ""),
        "api_key": rag.get("embedding_api_key") or llm.get("api_key", ""),
    }


def _merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result
