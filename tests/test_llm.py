"""Tests for the shared LLM client (mosaic/llm.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from mosaic import llm
from mosaic.errors import ConfigError


def _resp(payload: dict) -> MagicMock:
    r = MagicMock()
    r.is_error = False
    r.json.return_value = payload
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


class TestServerErrors:
    """The server's own reason must reach the user, not just "404 Not Found"."""

    def _post_returning(self, status: int, **kw) -> httpx.Response:
        req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
        return httpx.Response(status, request=req, **kw)

    def test_ollama_model_not_found(self):
        cfg = {
            "llm": {"provider": "openai", "api_key": "x", "base_url": "http://localhost:11434/v1"}
        }
        body = {"error": {"message": "model 'qwen-x' not found", "type": "not_found_error"}}
        with (
            patch("httpx.post", return_value=self._post_returning(404, json=body)),
            pytest.raises(llm.LLMRequestError) as exc_info,
        ):
            llm.complete("q", cfg)
        assert str(exc_info.value) == (
            "http://localhost:11434/v1 returned HTTP 404: model 'qwen-x' not found"
        )

    def test_anthropic_error_shape(self):
        cfg = {"llm": {"provider": "anthropic", "api_key": "bad"}}
        body = {
            "type": "error",
            "error": {"type": "authentication_error", "message": "invalid x-api-key"},
        }
        with (
            patch("httpx.post", return_value=self._post_returning(401, json=body)),
            pytest.raises(
                llm.LLMRequestError, match="anthropic returned HTTP 401: invalid x-api-key"
            ),
        ):
            llm.complete("q", cfg)

    def test_non_json_body_falls_back_to_text(self):
        cfg = {"llm": {"provider": "openai", "api_key": "sk"}}
        with (
            patch(
                "httpx.post", return_value=self._post_returning(502, text="Bad gateway upstream")
            ),
            pytest.raises(llm.LLMRequestError, match="HTTP 502: Bad gateway upstream"),
        ):
            llm.complete("q", cfg)

    def test_is_a_mosaic_error(self):
        from mosaic.errors import MosaicError

        assert issubclass(llm.LLMRequestError, MosaicError)


class TestOpenAIUrl:
    def test_versioned_and_bare_base_urls(self):
        from mosaic.llm import openai_url

        assert (
            openai_url("http://localhost:11434/v1", "embeddings")
            == "http://localhost:11434/v1/embeddings"
        )
        assert (
            openai_url("http://localhost:11434/v1/", "embeddings")
            == "http://localhost:11434/v1/embeddings"
        )
        assert openai_url("http://localhost:11434", "chat/completions") == (
            "http://localhost:11434/v1/chat/completions"
        )
        assert openai_url("https://example.org/v1beta/openai", "embeddings") == (
            "https://example.org/v1beta/openai/embeddings"
        )


class TestTimeout:
    def _ok(self) -> MagicMock:
        resp = MagicMock(is_error=False)
        resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        return resp

    def test_config_timeout_replaces_the_callers(self):
        cfg = {
            "llm": {"provider": "openai", "api_key": "k", "base_url": "http://h/v1", "timeout": 900}
        }
        with patch("mosaic.llm.httpx.post", return_value=self._ok()) as post:
            llm.complete("hi", cfg, timeout=120)
        assert post.call_args.kwargs["timeout"] == 900

    def test_zero_keeps_the_callers(self):
        cfg = {
            "llm": {"provider": "openai", "api_key": "k", "base_url": "http://h/v1", "timeout": 0}
        }
        with patch("mosaic.llm.httpx.post", return_value=self._ok()) as post:
            llm.complete("hi", cfg, timeout=120)
        assert post.call_args.kwargs["timeout"] == 120

    def test_config_flag_saves_it(self):
        from typer.testing import CliRunner

        from mosaic import config as cfg_mod
        from mosaic.cli import app

        cfg = cfg_mod._merge(cfg_mod._DEFAULTS, {})
        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.cfg_mod.save") as save,
        ):
            result = CliRunner().invoke(app, ["config", "--llm-timeout", "600"])
        assert result.exit_code == 0, result.output
        assert save.call_args.args[0]["llm"]["timeout"] == 600


class TestLoadsJson:
    def test_plain(self):
        assert llm.loads_json('[{"a": 1}]') == [{"a": 1}]

    def test_markdown_fence(self):
        assert llm.loads_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]

    def test_think_block_and_prose(self):
        text = '<think>the user wants</think>\nHere you are: {"scores": [0.5, 1]} Hope it helps.'
        assert llm.loads_json(text) == {"scores": [0.5, 1]}

    def test_no_json_raises(self):
        import json

        with pytest.raises(json.JSONDecodeError):
            llm.loads_json("I cannot help with that.")
