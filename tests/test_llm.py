"""Tests for the shared LLM client (mosaic/llm.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mosaic import llm
from mosaic.errors import ConfigError


def _resp(payload: dict) -> MagicMock:
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


_OPENAI_OK = _resp({"choices": [{"message": {"content": "hi from openai"}}]})
_ANTHROPIC_OK = _resp({"content": [{"text": "hi from claude"}]})


class TestResolve:
    def test_missing_config_raises_typed_error(self):
        with pytest.raises(llm.LLMConfigError) as exc_info:
            llm.resolve({})
        # Both hierarchies: project errors and legacy ``except ValueError`` handlers.
        assert isinstance(exc_info.value, ConfigError)
        assert isinstance(exc_info.value, ValueError)

    def test_unknown_provider_without_base_url_raises(self):
        with pytest.raises(llm.LLMConfigError, match="Unknown LLM provider"):
            llm.resolve({"llm": {"provider": "mistral", "api_key": "k"}})

    def test_unknown_provider_with_base_url_is_openai_compatible(self):
        cfg = {"llm": {"provider": "ollama", "api_key": "x", "base_url": "http://h:11434/v1/"}}
        s = llm.resolve(cfg)
        assert s.openai_compatible
        assert s.base_url == "http://h:11434/v1"
        assert s.model == ""

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "OpenAI"])
    def test_default_model_filled(self, provider):
        s = llm.resolve({"llm": {"provider": provider, "api_key": "k"}})
        assert s.model == llm.DEFAULT_MODELS[provider.lower()]

    def test_is_configured(self):
        assert llm.is_configured({"llm": {"provider": "openai", "api_key": "k"}})
        assert not llm.is_configured({"llm": {"provider": "openai"}})
        assert not llm.is_configured({})


class TestComplete:
    def test_openai_cloud_with_json_mode(self):
        cfg = {"llm": {"provider": "openai", "api_key": "sk"}}
        with patch("httpx.post", return_value=_OPENAI_OK) as post:
            out = llm.complete("q", cfg, json_mode=True)
        assert out == "hi from openai"
        url = post.call_args.args[0]
        body = post.call_args.kwargs["json"]
        assert url == "https://api.openai.com/v1/chat/completions"
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"] == [{"role": "user", "content": "q"}]
        assert "max_tokens" not in body

    def test_local_server_never_gets_response_format(self):
        cfg = {
            "llm": {"provider": "openai", "api_key": "x", "base_url": "http://localhost:1234/v1"}
        }
        with patch("httpx.post", return_value=_OPENAI_OK) as post:
            llm.complete("q", cfg, json_mode=True)
        assert post.call_args.args[0] == "http://localhost:1234/v1/chat/completions"
        assert "response_format" not in post.call_args.kwargs["json"]

    def test_anthropic_sends_max_tokens_and_version(self):
        cfg = {"llm": {"provider": "anthropic", "api_key": "ak", "model": "claude-x"}}
        with patch("httpx.post", return_value=_ANTHROPIC_OK) as post:
            out = llm.complete("q", cfg, max_tokens=256, json_mode=True)
        assert out == "hi from claude"
        headers = post.call_args.kwargs["headers"]
        body = post.call_args.kwargs["json"]
        assert headers["x-api-key"] == "ak"
        assert headers["anthropic-version"]
        assert body == {
            "model": "claude-x",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": "q"}],
        }

    def test_message_list_passed_through(self):
        cfg = {"llm": {"provider": "openai", "api_key": "sk"}}
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        with patch("httpx.post", return_value=_OPENAI_OK) as post:
            llm.complete(msgs, cfg)
        assert post.call_args.kwargs["json"]["messages"] == msgs

    def test_not_configured_makes_no_request(self):
        with patch("httpx.post") as post, pytest.raises(llm.LLMConfigError):
            llm.complete("q", {})
        post.assert_not_called()
