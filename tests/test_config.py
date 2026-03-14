"""Tests for configuration loading and merging."""

from unittest.mock import patch

import mosaic.config as cfg_mod


class TestLoadDefaults:
    def test_returns_defaults_when_no_file(self, tmp_path):
        fake_path = tmp_path / "nonexistent.toml"
        with patch.object(cfg_mod, "_CONFIG_PATH", fake_path):
            cfg = cfg_mod.load()
        assert "download_dir" in cfg
        assert "sources" in cfg
        assert cfg["sources"]["arxiv"]["enabled"] is True

    def test_all_sources_present_in_defaults(self, tmp_path):
        fake_path = tmp_path / "nonexistent.toml"
        with patch.object(cfg_mod, "_CONFIG_PATH", fake_path):
            cfg = cfg_mod.load()
        for src in ("arxiv", "semantic_scholar", "sciencedirect", "doaj", "europepmc"):
            assert src in cfg["sources"]


class TestMerge:
    def test_user_value_overrides_default(self):
        merged = cfg_mod._merge({"a": 1, "b": 2}, {"b": 99})
        assert merged["b"] == 99
        assert merged["a"] == 1

    def test_nested_dict_merged_not_replaced(self):
        defaults = {"sources": {"arxiv": {"enabled": True}, "doaj": {"enabled": True}}}
        overrides = {"sources": {"arxiv": {"enabled": False}}}
        merged = cfg_mod._merge(defaults, overrides)
        assert merged["sources"]["arxiv"]["enabled"] is False
        assert merged["sources"]["doaj"]["enabled"] is True  # not wiped out

    def test_scalar_override_replaces_entirely(self):
        merged = cfg_mod._merge({"x": [1, 2]}, {"x": [3]})
        assert merged["x"] == [3]


class TestSaveAndLoad:
    def test_roundtrip(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg = cfg_mod._merge(cfg_mod._DEFAULTS, {})
        cfg["unpaywall"]["email"] = "test@example.com"
        with patch.object(cfg_mod, "_CONFIG_PATH", cfg_path):
            cfg_mod.save(cfg)
            loaded = cfg_mod.load()
        assert loaded["unpaywall"]["email"] == "test@example.com"
