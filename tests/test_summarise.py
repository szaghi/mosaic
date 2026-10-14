"""Tests for ``mosaic search --summarise`` (issue #14)."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from mosaic.cli import app
from mosaic.models import Paper
from mosaic.summarise import ABSTRACT_CHARS, MAX_PAPERS, build_prompt, summarise

runner = CliRunner()
_LLM = {"llm": {"provider": "openai", "api_key": "sk"}}


def _p(n: int, abstract: str | None = "An abstract.", year: int | None = 2024) -> Paper:
    return Paper(title=f"Paper {n}", doi=f"10.1/{n}", year=year, abstract=abstract, source="arXiv")


class TestBuildPrompt:
    def test_numbers_follow_display_order(self):
        prompt = build_prompt("q", [_p(7), _p(3)])
        assert prompt.index("[1] Paper 7 (2024)") < prompt.index("[2] Paper 3 (2024)")

    def test_missing_abstract_and_year_are_explicit(self):
        prompt = build_prompt("q", [_p(1, abstract=None, year=None)])
        assert "[1] Paper 1 (n.d.)\n(no abstract)" in prompt

    def test_long_abstract_truncated_at_word_boundary(self):
        prompt = build_prompt("q", [_p(1, abstract="word " * 1000)])
        body = prompt.split("[1] Paper 1 (2024)\n", 1)[1]
        assert body.endswith("word ...\n") or body.rstrip().endswith("word ...")
        assert len(body) <= ABSTRACT_CHARS + 10

    def test_truncated_to_max_papers_and_says_so(self):
        papers = [_p(i) for i in range(MAX_PAPERS + 5)]
        prompt = build_prompt("q", papers)
        assert f"[{MAX_PAPERS}] " in prompt
        assert f"[{MAX_PAPERS + 1}] " not in prompt
        assert f"first {MAX_PAPERS} of {MAX_PAPERS + 5}" in prompt


class TestSummarise:
    def test_no_abstracts_makes_no_llm_call(self):
        with patch("mosaic.llm.complete") as complete:
            assert summarise("q", [_p(1, abstract=None)], _LLM) is None
        complete.assert_not_called()

    def test_returns_stripped_llm_text(self):
        with patch("mosaic.llm.complete", return_value="  Themes [1].\n") as complete:
            assert summarise("q", [_p(1)], _LLM) == "Themes [1]."
        assert complete.call_args.kwargs["max_tokens"] == 600


@pytest.fixture
def search_env(tmp_cache):
    def _run(args, cfg_extra=None, papers=None):
        cfg = {
            "db_path": ":memory:",
            "download_dir": "/tmp/x",
            "sources": {},
            "unpaywall": {"email": ""},
            **(cfg_extra or {}),
        }
        with (
            patch("mosaic.cli.cfg_mod.load", return_value=cfg),
            patch("mosaic.cli.Cache", return_value=tmp_cache),
            patch("mosaic.cli.build_sources", return_value=[]),
            patch("mosaic.cli.search_all", return_value=papers or [_p(1), _p(2)]),
        ):
            return runner.invoke(app, ["search", "diffusion", *args])

    return _run


class TestSearchSummariseCli:
    def test_table_mode_prints_panel(self, search_env):
        with patch("mosaic.summarise.llm.complete", return_value="Two themes [1][2]."):
            r = search_env(["--summarise"], cfg_extra=_LLM)
        assert r.exit_code == 0, r.output
        assert "AI summary" in r.output
        assert "Two themes [1][2]." in r.output

    def test_american_spelling_alias(self, search_env):
        with patch("mosaic.summarise.llm.complete", return_value="ok"):
            r = search_env(["--summarize"], cfg_extra=_LLM)
        assert "AI summary" in r.output

    def test_no_llm_configured_is_a_hint_not_an_error(self, search_env):
        r = search_env(["--summarise"])
        assert r.exit_code == 0
        assert "--summarise skipped" in r.output
        assert "Paper 1" in r.output  # results still shown

    def test_llm_failure_is_not_fatal(self, search_env):
        with patch("mosaic.summarise.llm.complete", side_effect=httpx.ConnectError("down")):
            r = search_env(["--summarise"], cfg_extra=_LLM)
        assert r.exit_code == 0
        assert "--summarise failed: down" in r.output

    def test_json_includes_summary(self, search_env):
        with patch("mosaic.summarise.llm.complete", return_value="Synthesis [1]."):
            r = search_env(["--summarise", "--json"], cfg_extra=_LLM)
        out = json.loads(r.output)
        assert out["summary"] == "Synthesis [1]."
        assert out["errors"] == []

    def test_json_summary_null_with_reason_when_skipped(self, search_env):
        r = search_env(["--summarise", "--json"])
        out = json.loads(r.output)
        assert out["summary"] is None
        assert any("--summarise skipped" in e for e in out["errors"])

    def test_json_without_flag_has_no_summary_key(self, search_env):
        out = json.loads(search_env(["--json"]).output)
        assert "summary" not in out

    def test_without_flag_no_llm_call(self, search_env):
        with patch("mosaic.summarise.llm.complete") as complete:
            search_env([], cfg_extra=_LLM)
        complete.assert_not_called()
