"""Shared helpers used by both the CLI and the web UI."""
from __future__ import annotations

from mosaic.sources import (
    ArxivSource, SemanticScholarSource, ScienceDirectSource,
    ScienceDirectBrowserSource, SpringerBrowserSource,
    BioRxivSource, DoajSource, EuropePMCSource, OpenAlexSource, BASESource, CORESource,
    NASAADSSource, IEEEXploreSource, ZenodoSource, CrossrefSource,
    SpringerAPISource, CustomSource, DBLPSource, HALSource, PubMedSource, PMCSource,
    PEDroSource, ScopusAPISource, ScopusBrowserSource,
)

# Source shorthand → display name mapping
SRC_MAP: dict[str, str] = {
    "arxiv": "arXiv", "ss": "Semantic Scholar",
    "sd": "ScienceDirect", "doaj": "DOAJ", "epmc": "Europe PMC",
    "oa": "OpenAlex", "base": "BASE", "core": "CORE",
    "sp": "Springer", "springer": "Springer Nature",
    "ads": "NASA ADS", "ieee": "IEEE Xplore",
    "zenodo": "Zenodo", "crossref": "Crossref",
    "dblp": "DBLP", "hal": "HAL", "pubmed": "PubMed", "pmc": "PubMed Central",
    "rxiv": "bioRxiv/medRxiv",
    "pedro": "PEDro",
    "scopus": "Scopus",
}


def build_sources(cfg: dict) -> list:
    """Instantiate all enabled sources from the given config dict."""
    src_cfg = cfg.get("sources", {})
    sources = []
    if src_cfg.get("arxiv", {}).get("enabled", True):
        sources.append(ArxivSource(delay=cfg.get("rate_limit_delay", 3.0)))
    if src_cfg.get("semantic_scholar", {}).get("enabled", True):
        sources.append(SemanticScholarSource(
            api_key=src_cfg.get("semantic_scholar", {}).get("api_key", "")
        ))
    if src_cfg.get("sciencedirect", {}).get("enabled", True):
        api_key = src_cfg.get("sciencedirect", {}).get("api_key", "")
        if api_key:
            sources.append(ScienceDirectSource(api_key=api_key, open_access_only=True))
        else:
            browser_src = ScienceDirectBrowserSource()
            if browser_src.available():
                sources.append(browser_src)
    if src_cfg.get("doaj", {}).get("enabled", True):
        sources.append(DoajSource())
    if src_cfg.get("europepmc", {}).get("enabled", True):
        sources.append(EuropePMCSource())
    if src_cfg.get("openalex", {}).get("enabled", True):
        sources.append(OpenAlexSource(email=cfg.get("unpaywall", {}).get("email", "")))
    if src_cfg.get("base", {}).get("enabled", True):
        sources.append(BASESource())
    if src_cfg.get("core", {}).get("enabled", True):
        sources.append(CORESource(api_key=src_cfg.get("core", {}).get("api_key", "")))
    if src_cfg.get("nasa_ads", {}).get("enabled", True):
        sources.append(NASAADSSource(api_key=src_cfg.get("nasa_ads", {}).get("api_key", "")))
    if src_cfg.get("ieee", {}).get("enabled", True):
        sources.append(IEEEXploreSource(api_key=src_cfg.get("ieee", {}).get("api_key", "")))
    if src_cfg.get("zenodo", {}).get("enabled", True):
        sources.append(ZenodoSource(api_key=src_cfg.get("zenodo", {}).get("api_key", "")))
    if src_cfg.get("crossref", {}).get("enabled", True):
        sources.append(CrossrefSource(email=cfg.get("unpaywall", {}).get("email", "")))
    if src_cfg.get("springer_api", {}).get("enabled", True):
        sources.append(SpringerAPISource(api_key=src_cfg.get("springer_api", {}).get("api_key", "")))
    if src_cfg.get("dblp", {}).get("enabled", True):
        sources.append(DBLPSource())
    if src_cfg.get("hal", {}).get("enabled", True):
        sources.append(HALSource())
    if src_cfg.get("pubmed", {}).get("enabled", True):
        sources.append(PubMedSource(api_key=src_cfg.get("pubmed", {}).get("api_key", "")))
    if src_cfg.get("pmc", {}).get("enabled", True):
        sources.append(PMCSource(api_key=src_cfg.get("pmc", {}).get("api_key", "")))
    if src_cfg.get("biorxiv", {}).get("enabled", True):
        sources.append(BioRxivSource())
    pedro_cfg = src_cfg.get("pedro", {})
    if pedro_cfg.get("enabled", True):
        pedro_src = PEDroSource(
            acknowledge_fair_use=pedro_cfg.get("acknowledge_fair_use", False),
            rate_limit_delay=pedro_cfg.get("rate_limit_delay", 3.0),
            fetch_details=pedro_cfg.get("fetch_details", False),
        )
        if pedro_src.available():
            sources.append(pedro_src)
    if src_cfg.get("springer", {}).get("enabled", True):
        springer_src = SpringerBrowserSource()
        if springer_src.available():
            sources.append(springer_src)
    if src_cfg.get("scopus", {}).get("enabled", True):
        scopus_api_key = src_cfg.get("scopus", {}).get("api_key", "")
        scopus_inst_token = src_cfg.get("scopus", {}).get("inst_token", "")
        if scopus_api_key:
            sources.append(ScopusAPISource(api_key=scopus_api_key, inst_token=scopus_inst_token))
        else:
            scopus_browser = ScopusBrowserSource()
            if scopus_browser.available():
                sources.append(scopus_browser)
    for custom_cfg in cfg.get("custom_sources", []):
        if custom_cfg.get("enabled", True):
            sources.append(CustomSource(custom_cfg))
    return sources
