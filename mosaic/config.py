"""Configuration management (~/.config/mosaic/config.toml)."""
from __future__ import annotations
import tomllib
import tomli_w
from pathlib import Path

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
    },
    "unpaywall": {"email": ""},
    "custom_sources": [],
}


def load() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        # merge missing keys from defaults
        return _merge(_DEFAULTS, data)
    return dict(_DEFAULTS)


def save(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)


def _merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result
