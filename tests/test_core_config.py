"""Config robustness: no shared defaults, atomic saves, permissions, parse errors."""

from __future__ import annotations

import os
import stat
from unittest.mock import patch

import pytest

import mosaic.config as cfg_mod
from mosaic.config import apply_api_keys, get_embedding_cfg
from mosaic.errors import ConfigError


class TestNoSharedDefaults:
    def test_mutating_loaded_defaults_does_not_touch_module_defaults(self, tmp_path):
        with patch.object(cfg_mod, "_CONFIG_PATH", tmp_path / "missing.toml"):
            cfg = cfg_mod.load()
        apply_api_keys(cfg, {"core_key": "SECRET"})
        cfg["obsidian"]["tags"].append("leak")
        assert cfg_mod._DEFAULTS["sources"]["core"]["api_key"] == ""
        assert cfg_mod._DEFAULTS["obsidian"]["tags"] == ["paper"]

    def test_sections_absent_from_file_are_not_shared(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('download_dir = "/x"\n')
        with patch.object(cfg_mod, "_CONFIG_PATH", path):
            cfg = cfg_mod.load()
        cfg["zotero"]["api_key"] = "k"
        cfg["sources"]["core"]["api_key"] = "k"
        cfg["custom_sources"].append({"name": "x"})
        assert cfg_mod._DEFAULTS["zotero"]["api_key"] == ""
        assert cfg_mod._DEFAULTS["sources"]["core"]["api_key"] == ""
        assert cfg_mod._DEFAULTS["custom_sources"] == []

    def test_two_loads_are_independent(self, tmp_path):
        with patch.object(cfg_mod, "_CONFIG_PATH", tmp_path / "missing.toml"):
            a = cfg_mod.load()
            a["llm"]["api_key"] = "sk-a"
            b = cfg_mod.load()
        assert b["llm"]["api_key"] == ""

    def test_merge_does_not_alias_override_values(self):
        overrides = {"obsidian": {"tags": ["a"]}}
        merged = cfg_mod._merge({"obsidian": {"tags": ["paper"]}}, overrides)
        merged["obsidian"]["tags"].append("b")
        assert overrides["obsidian"]["tags"] == ["a"]


class TestLoadErrors:
    def test_invalid_toml_raises_config_error_with_path(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("this is = = not toml\n")
        with patch.object(cfg_mod, "_CONFIG_PATH", path):
            with pytest.raises(ConfigError, match=str(path)):
                cfg_mod.load()


class TestAtomicSave:
    def test_existing_loose_permissions_are_tightened(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('download_dir = "/old"\n')
        os.chmod(path, 0o644)
        with patch.object(cfg_mod, "_CONFIG_PATH", path):
            cfg_mod.save({"download_dir": "/new"})
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert "/new" in path.read_text()

    def test_new_file_is_owner_only(self, tmp_path):
        path = tmp_path / "sub" / "config.toml"
        with patch.object(cfg_mod, "_CONFIG_PATH", path):
            cfg_mod.save({"download_dir": "/x"})
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_failed_serialisation_keeps_old_file_and_leaves_no_temp(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('download_dir = "/old"\n')
        with patch.object(cfg_mod, "_CONFIG_PATH", path):
            with pytest.raises(TypeError):
                cfg_mod.save({"download_dir": "/new", "bad": object()})
        assert path.read_text() == 'download_dir = "/old"\n'
        assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


class TestEmbeddingKeyInheritance:
    def _cfg(self, provider, api_key="llm-key", base_url="", emb_base="", emb_key=""):
        return {
            "rag": {
                "embedding_model": "m",
                "embedding_base_url": emb_base,
                "embedding_api_key": emb_key,
                "embedding_provider": "",
            },
            "llm": {"provider": provider, "api_key": api_key, "base_url": base_url},
        }

    def test_anthropic_key_not_inherited(self):
        emb = get_embedding_cfg(self._cfg("anthropic", api_key="sk-ant-secret"))
        assert emb["api_key"] == ""
        assert emb["base_url"] == ""

    def test_anthropic_key_not_sent_to_custom_embedding_server(self):
        emb = get_embedding_cfg(
            self._cfg("anthropic", api_key="sk-ant-secret", emb_base="http://localhost:11434/v1")
        )
        assert emb["api_key"] == ""
        assert emb["base_url"] == "http://localhost:11434/v1"

    def test_openai_key_inherited(self):
        emb = get_embedding_cfg(self._cfg("openai", api_key="sk-openai"))
        assert emb["api_key"] == "sk-openai"

    def test_custom_llm_base_url_key_inherited(self):
        emb = get_embedding_cfg(self._cfg("anthropic", base_url="http://llm:8080/v1"))
        assert emb["api_key"] == "llm-key"
        assert emb["base_url"] == "http://llm:8080/v1"

    def test_explicit_embedding_key_always_wins(self):
        emb = get_embedding_cfg(self._cfg("anthropic", emb_key="emb-key"))
        assert emb["api_key"] == "emb-key"
