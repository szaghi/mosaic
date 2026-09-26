"""Tests for mosaic.source_registry — factories and selectable source keys."""

from mosaic.source_registry import (
    SRC_MAP,
    build_sources,
    custom_source_key,
    source_choices,
)
from mosaic.sources import ArxivSource, ScienceDirectSource


def _only(cfg_sources: dict) -> dict:
    """Config enabling only the given sources (everything else disabled)."""
    all_keys = [
        "arxiv", "semantic_scholar", "sciencedirect", "doaj", "europepmc", "openalex",
        "base", "core", "nasa_ads", "ieee", "zenodo", "crossref", "springer_api", "dblp",
        "hal", "pubmed", "pmc", "biorxiv", "pedro", "springer", "scopus",
    ]  # fmt: skip
    sources = {k: {"enabled": False} for k in all_keys}
    for key, value in cfg_sources.items():
        sources[key] = {"enabled": True, **value}
    return {"sources": sources}


class TestArxivDelay:
    def _arxiv(self, cfg):
        (src,) = build_sources(cfg)
        assert isinstance(src, ArxivSource)
        return src

    def test_default_respects_arxiv_minimum(self):
        # The global rate_limit_delay defaults to 1 s — too fast for arXiv.
        cfg = {**_only({"arxiv": {}}), "rate_limit_delay": 1.0}
        assert self._arxiv(cfg)._delay == 3.0

    def test_larger_global_delay_honoured(self):
        cfg = {**_only({"arxiv": {}}), "rate_limit_delay": 5.0}
        assert self._arxiv(cfg)._delay == 5.0

    def test_arxiv_specific_delay_wins(self):
        cfg = {**_only({"arxiv": {"rate_limit_delay": 0.5}}), "rate_limit_delay": 5.0}
        assert self._arxiv(cfg)._delay == 0.5


class TestScienceDirectInstToken:
    def test_own_inst_token(self):
        cfg = _only({"sciencedirect": {"api_key": "k", "inst_token": "T1"}})
        (src,) = build_sources(cfg)
        assert isinstance(src, ScienceDirectSource)
        assert src._inst_token == "T1"

    def test_falls_back_to_scopus_inst_token(self):
        cfg = _only({"sciencedirect": {"api_key": "k"}})
        cfg["sources"]["scopus"] = {"enabled": False, "inst_token": "SCOPUS-T"}
        (src,) = build_sources(cfg)
        assert src._inst_token == "SCOPUS-T"


class TestSourceChoices:
    def test_builtins_present(self):
        assert source_choices({}) == SRC_MAP

    def test_custom_sources_added(self):
        cfg = {
            "custom_sources": [
                {"name": "My Lab API", "url": "https://lab.example/api"},
                {"name": "Disabled One", "url": "https://x", "enabled": False},
                {"url": "https://nameless"},
            ]
        }
        choices = source_choices(cfg)
        assert choices["my-lab-api"] == "My Lab API"
        assert "disabled-one" not in choices
        assert len(choices) == len(SRC_MAP) + 1

    def test_custom_key_matches_built_source_name(self):
        cfg = {"custom_sources": [{"name": "My Lab API", "url": "https://lab.example/api"}]}
        names = {s.name for s in build_sources({**cfg, **_only({})})}
        assert source_choices(cfg)["my-lab-api"] in names

    def test_collision_with_builtin_prefixed(self):
        assert custom_source_key("arXiv") == "custom-arxiv"
        assert custom_source_key("  Weird  Name!! ") == "weird-name"
