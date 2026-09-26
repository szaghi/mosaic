"""CLI tests (Typer CliRunner) for the behaviours fixed during the code review.

The autouse ``_isolated_user_files`` fixture in conftest points the config file,
cache DB and download dir at a temporary directory.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import mosaic.config as cfg_mod
from mosaic.cli import app
from mosaic.db import Cache
from mosaic.models import Paper

runner = CliRunner()


def _cache() -> Cache:
    return Cache(cfg_mod.load()["db_path"])


def _seed(*papers: Paper) -> None:
    with _cache() as cache:
        for p in papers:
            cache.save(p)


class TestSearch:
    def test_cached_json_applies_filters_and_sort(self):
        _seed(
            Paper(title="Graph A", doi="10.1/a", year=2019, source="s", is_open_access=False),
            Paper(title="Graph B", doi="10.1/b", year=2023, source="s", is_open_access=True),
            Paper(title="Graph C", doi="10.1/c", year=2021, source="s", is_open_access=True),
        )
        result = runner.invoke(
            app, ["search", "Graph", "--cached", "--json", "--oa-only", "--sort", "year"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert [p["title"] for p in data["papers"]] == ["Graph B", "Graph C"]

    def test_cached_json_writes_output_file(self, tmp_path):
        _seed(Paper(title="Graph A", doi="10.1/a", source="s"))
        out = tmp_path / "out.ris"
        result = runner.invoke(app, ["search", "Graph", "--cached", "--json", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.read_text().startswith("TY  -")
        json.loads(result.output)  # stdout stays pure JSON

    def test_unknown_sort_rejected(self):
        result = runner.invoke(app, ["search", "q", "--sort", "bogus"])
        assert result.exit_code == 1
        assert "Unknown --sort" in result.output

    def test_custom_source_selectable(self):
        src = MagicMock()
        src.name = "My Repo"
        with (
            patch("mosaic.cli.build_sources", return_value=[src]),
            patch("mosaic.cli.source_choices", return_value={"myrepo": "My Repo"}),
            patch("mosaic.cli.search_all", return_value=[]) as search,
        ):
            result = runner.invoke(app, ["search", "q", "--source", "myrepo", "--json"])
        assert result.exit_code == 0, result.output
        assert search.call_args.args[0] == [src]

    def test_search_is_logged_for_history(self):
        with (
            patch("mosaic.cli.build_sources", return_value=[]),
            patch("mosaic.cli.search_all", return_value=[Paper(title="T", doi="10.1/t")]),
        ):
            runner.invoke(app, ["search", "logged query", "--json", "--year", "2020"])
        with _cache() as cache:
            entry = cache.list_searches()[0]
        assert entry["query"] == "logged query"
        assert json.loads(entry["filters_json"])["year"] == "2020"


class TestAutoIndex:
    def test_failure_is_reported(self):
        cfg = cfg_mod.load()
        cfg["rag"]["auto_index"] = True
        cfg_mod.save(cfg)
        with (
            patch("mosaic.workflows.dl_paper", return_value=None),
            patch("mosaic.rag.index_papers", side_effect=ValueError("No embedding model")),
        ):
            result = runner.invoke(app, ["get", "10.1/x"])
        assert "Auto-index failed: No embedding model" in result.output


class TestIndex:
    def test_from_file_finds_cached_dois(self, tmp_path):
        _seed(
            Paper(title="Wanted", doi="10.1/wanted", source="s"),
            Paper(title="Other", doi="10.1/other", source="s"),
        )
        refs = tmp_path / "refs.csv"
        refs.write_text("doi\nhttps://doi.org/10.1/WANTED\n")
        with patch("mosaic.rag.index_papers", return_value=(1, 0, 0)) as idx:
            result = runner.invoke(app, ["index", "--from", str(refs), "--batch-size", "8"])
        assert result.exit_code == 0, result.output
        assert [p.title for p in idx.call_args.args[0]] == ["Wanted"]
        assert idx.call_args.kwargs["batch_size"] == 8

    def test_runtime_errors_are_friendly(self):
        _seed(Paper(title="P", doi="10.1/p", source="s"))
        with patch("mosaic.rag.index_papers", side_effect=RuntimeError("Embedding request failed")):
            result = runner.invoke(app, ["index"])
        assert result.exit_code == 1
        assert "Embedding request failed" in result.output


class TestAsk:
    def test_empty_subset_is_not_the_whole_library(self):
        _seed(Paper(title="Unrelated", doi="10.1/u", source="s"))
        with patch("mosaic.rag.ask", return_value=("none", [])) as ask:
            result = runner.invoke(app, ["ask", "Why?", "--query", "no-such-topic"])
        assert result.exit_code == 0, result.output
        assert ask.call_args.kwargs["pre_filter"] == []

    def test_invalid_year_rejected(self):
        result = runner.invoke(app, ["ask", "Why?", "--year", "20x"])
        assert result.exit_code == 1
        assert "Invalid year" in result.output

    def test_output_markdown(self, tmp_path):
        paper = Paper(title="Source", authors=["A B"], year=2020, doi="10.1/s")
        out = tmp_path / "answer.md"
        with patch("mosaic.rag.ask", return_value=("Answer text", [paper])):
            result = runner.invoke(app, ["ask", "Why?", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.read_text().startswith("# Why?")


class TestChat:
    def test_turns_share_history(self):
        paper = Paper(title="P", doi="10.1/p")
        with patch("mosaic.rag.chat_turn", side_effect=[("A1", [paper]), ("A2", [paper])]) as turn:
            result = runner.invoke(app, ["chat"], input="Q1\nQ2\n/quit\n")
        assert result.exit_code == 0, result.output
        second_history = turn.call_args_list[1].args[1]
        assert second_history == [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]

    def test_invalid_mode(self):
        result = runner.invoke(app, ["chat", "--mode", "poetry"])
        assert result.exit_code == 1


class TestCompare:
    def test_errors_are_printed_and_sort_validated(self):
        _seed(Paper(title="Diffusion paper", doi="10.1/d", source="s"))

        def fake_compare(papers, dims, cfg, errors=None):
            errors.append("LLM batch 1 failed")
            return [dict.fromkeys(dims, "-") for _ in papers]

        with patch("mosaic.compare.compare_papers", side_effect=fake_compare):
            result = runner.invoke(app, ["compare", "-q", "Diffusion"])
        assert result.exit_code == 0, result.output
        assert "LLM batch 1 failed" in result.output
        assert runner.invoke(app, ["compare", "--sort", "stars"]).exit_code == 1


class TestConfig:
    def test_chunk_overlap_must_be_smaller_than_chunk_size(self):
        result = runner.invoke(app, ["config", "--chunk-size", "100", "--chunk-overlap", "100"])
        assert result.exit_code == 1

    def test_rag_parity_options_saved(self):
        result = runner.invoke(
            app,
            ["config", "--chunk-size", "256", "--rag-citations", "--embedding-provider", "openai"],
        )
        assert result.exit_code == 0, result.output
        rag = cfg_mod.load()["rag"]
        assert rag["chunk_size"] == 256
        assert rag["citations"]["enabled"] is True
        assert rag["embedding_provider"] == "openai"

    def test_broken_config_file_is_reported_without_traceback(self, capsys):
        cfg_mod._CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg_mod._CONFIG_PATH.write_text("this is = = not toml")
        with pytest.raises(SystemExit) as exc:
            app(["config", "--show"])
        assert exc.value.code == 1
        assert "Could not parse config file" in capsys.readouterr().out


class TestAuthAndNotebook:
    def test_logout_unknown_session(self):
        with patch("mosaic.auth.delete_session", return_value=False):
            result = runner.invoke(app, ["auth", "logout", "nope"])
        assert result.exit_code == 1
        assert "No session found" in result.output

    def test_notebook_preflight(self):
        with patch(
            "mosaic.notebooklm_bridge.preflight_error",
            return_value="NotebookLM is not authenticated. Run `notebooklm login`",
        ):
            result = runner.invoke(app, ["notebook", "create", "NB", "--query", "q"])
        assert result.exit_code == 1
        assert "notebooklm login" in result.output


class TestUiCommand:
    def _run(self, *args):
        server = MagicMock()
        with (
            patch("mosaic.ui.create_app") as create_app,
            patch("waitress.create_server", return_value=server),
        ):
            result = runner.invoke(app, ["ui", "--no-browser", *args])
        return result, create_app

    def test_loopback_has_no_token(self):
        result, create_app = self._run()
        assert result.exit_code == 0, result.output
        assert create_app.call_args.kwargs["access_token"] is None

    def test_network_bind_generates_token(self):
        result, create_app = self._run("--host", "0.0.0.0")
        token = create_app.call_args.kwargs["access_token"]
        assert token and len(token) >= 24
        assert f"?token={token}" in result.output.replace("\n", "")

    def test_explicit_token_and_no_auth(self):
        _, create_app = self._run("--host", "0.0.0.0", "--token", "mine")
        assert create_app.call_args.kwargs["access_token"] == "mine"
        result, create_app = self._run("--host", "0.0.0.0", "--no-auth")
        assert create_app.call_args.kwargs["access_token"] is None
        assert "--no-auth" in result.output
