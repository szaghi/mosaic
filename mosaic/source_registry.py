"""Shared helpers used by both the CLI and the web UI."""

from __future__ import annotations

from collections.abc import Callable

from mosaic.sources import (
    ArxivSource,
    BASESource,
    BioRxivSource,
    CORESource,
    CrossrefSource,
    CustomSource,
    DBLPSource,
    DoajSource,
    EuropePMCSource,
    HALSource,
    IEEEXploreSource,
    NASAADSSource,
    OpenAlexSource,
    PEDroSource,
    PMCSource,
    PubMedSource,
    ScienceDirectBrowserSource,
    ScienceDirectSource,
    ScopusAPISource,
    ScopusBrowserSource,
    SemanticScholarSource,
    SpringerAPISource,
    SpringerBrowserSource,
    ZenodoSource,
)
from mosaic.sources.base import BaseSource

# Source shorthand → display name mapping
SRC_MAP: dict[str, str] = {
    "arxiv": "arXiv",
    "ss": "Semantic Scholar",
    "sd": "ScienceDirect",
    "doaj": "DOAJ",
    "epmc": "Europe PMC",
    "oa": "OpenAlex",
    "base": "BASE",
    "core": "CORE",
    "sp": "Springer",
    "springer": "Springer Nature",
    "ads": "NASA ADS",
    "ieee": "IEEE Xplore",
    "zenodo": "Zenodo",
    "crossref": "Crossref",
    "dblp": "DBLP",
    "hal": "HAL",
    "pubmed": "PubMed",
    "pmc": "PubMed Central",
    "rxiv": "bioRxiv/medRxiv",
    "pedro": "PEDro",
    "scopus": "Scopus",
}

# Shorthand → config key mapping (used by both CLI and UI)
SHORTHAND_TO_CFG_KEY: dict[str, str] = {
    "arxiv": "arxiv",
    "ss": "semantic_scholar",
    "sd": "sciencedirect",
    "doaj": "doaj",
    "epmc": "europepmc",
    "oa": "openalex",
    "base": "base",
    "core": "core",
    "sp": "springer",
    "springer": "springer_api",
    "ads": "nasa_ads",
    "ieee": "ieee",
    "zenodo": "zenodo",
    "crossref": "crossref",
    "dblp": "dblp",
    "hal": "hal",
    "pubmed": "pubmed",
    "pmc": "pmc",
    "rxiv": "biorxiv",
    "pedro": "pedro",
    "scopus": "scopus",
}


# ---------------------------------------------------------------------------
# Factory helpers for common patterns
# ---------------------------------------------------------------------------

_Factory = Callable[[dict, dict], BaseSource | None]


def _no_args(cls: type[BaseSource]) -> _Factory:
    """Factory for sources that take no constructor arguments."""
    return lambda _cfg, _src: cls()


def _api_key(cls: type[BaseSource]) -> _Factory:
    """Factory for sources that take ``api_key`` from source config."""
    return lambda _cfg, src: cls(api_key=src.get("api_key", ""))


def _email(cls: type[BaseSource]) -> _Factory:
    """Factory for sources that take ``email`` from unpaywall config."""
    return lambda cfg, _src: cls(email=cfg.get("unpaywall", {}).get("email", ""))


# ---------------------------------------------------------------------------
# Custom factories — sources with non-trivial construction logic
# ---------------------------------------------------------------------------


def _make_arxiv(cfg: dict, _src: dict) -> BaseSource:
    return ArxivSource(delay=cfg.get("rate_limit_delay", 3.0))


def _make_sciencedirect(_cfg: dict, src: dict) -> BaseSource | None:
    api_key = src.get("api_key", "")
    if api_key:
        return ScienceDirectSource(api_key=api_key, open_access_only=True)
    browser = ScienceDirectBrowserSource()
    return browser if browser.available() else None


def _make_pedro(_cfg: dict, src: dict) -> BaseSource | None:
    pedro = PEDroSource(
        acknowledge_fair_use=src.get("acknowledge_fair_use", False),
        rate_limit_delay=src.get("rate_limit_delay", 3.0),
        fetch_details=src.get("fetch_details", False),
    )
    return pedro if pedro.available() else None


def _make_springer_browser(_cfg: dict, _src: dict) -> BaseSource | None:
    browser = SpringerBrowserSource()
    return browser if browser.available() else None


def _make_scopus(_cfg: dict, src: dict) -> BaseSource | None:
    api_key = src.get("api_key", "")
    inst_token = src.get("inst_token", "")
    if api_key:
        return ScopusAPISource(api_key=api_key, inst_token=inst_token)
    browser = ScopusBrowserSource()
    return browser if browser.available() else None


# ---------------------------------------------------------------------------
# Source registry — each entry is (config_key, factory)
# ---------------------------------------------------------------------------

_SOURCE_REGISTRY: list[tuple[str, _Factory]] = [
    ("arxiv", _make_arxiv),
    ("semantic_scholar", _api_key(SemanticScholarSource)),
    ("sciencedirect", _make_sciencedirect),
    ("doaj", _no_args(DoajSource)),
    ("europepmc", _no_args(EuropePMCSource)),
    ("openalex", _email(OpenAlexSource)),
    ("base", _no_args(BASESource)),
    ("core", _api_key(CORESource)),
    ("nasa_ads", _api_key(NASAADSSource)),
    ("ieee", _api_key(IEEEXploreSource)),
    ("zenodo", _api_key(ZenodoSource)),
    ("crossref", _email(CrossrefSource)),
    ("springer_api", _api_key(SpringerAPISource)),
    ("dblp", _no_args(DBLPSource)),
    ("hal", _no_args(HALSource)),
    ("pubmed", _api_key(PubMedSource)),
    ("pmc", _api_key(PMCSource)),
    ("biorxiv", _no_args(BioRxivSource)),
    ("pedro", _make_pedro),
    ("springer", _make_springer_browser),
    ("scopus", _make_scopus),
]


def build_sources(cfg: dict) -> list[BaseSource]:
    """Instantiate all enabled sources from the given config dict."""
    src_cfg = cfg.get("sources", {})
    sources: list[BaseSource] = []

    for key, factory in _SOURCE_REGISTRY:
        entry_cfg = src_cfg.get(key, {})
        if not entry_cfg.get("enabled", True):
            continue
        source = factory(cfg, entry_cfg)
        if source is not None:
            sources.append(source)

    # Custom sources defined in config
    for custom_cfg in cfg.get("custom_sources", []):
        if custom_cfg.get("enabled", True):
            sources.append(CustomSource(custom_cfg))

    return sources
