"""Tests for saved-search watches (issue #17)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mosaic.cli import app
from mosaic.errors import ConfigError
from mosaic.models import Paper
from mosaic.watch import WatchSpec, run_watch

runner = CliRunner()


def _p(n: int, **kw) -> Paper:
    return Paper(title=f"Paper {n}", doi=f"10.1/{n}", source="arXiv", year=2025, **kw)


@pytest.fixture
def cfg(tmp_path):
    return {
        "db_path": str(tmp_path / "c.db"),
        "download_dir": str(tmp_path / "dl"),
        "sources": {},
        "unpaywall": {"email": ""},
    }


def _search_returning(*batches: list[Paper]):
    """Patch the fan-out so successive runs return *batches* in order."""
    it = iter(batches)
    return patch("mosaic.watch.search_all", side_effect=lambda *a, **k: list(next(it)))


# ── Cache layer ──────────────────────────────────────────────────────────────


class TestWatchStorage:
    def test_add_get_list_remove(self, tmp_cache):
        wid = tmp_cache.add_watch("t", WatchSpec("q").to_json())
        assert tmp_cache.get_watch("t")["id"] == wid
        assert [w["name"] for w in tmp_cache.list_watches()] == ["t"]
        assert tmp_cache.remove_watch("t") is True
        assert tmp_cache.get_watch("t") is None
        assert tmp_cache.remove_watch("t") is False

    def test_duplicate_name_rejected(self, tmp_cache):
        import sqlite3

        tmp_cache.add_watch("t", "{}")
        with pytest.raises(sqlite3.IntegrityError):
            tmp_cache.add_watch("t", "{}")

    def test_record_hits_returns_only_unseen_and_stamps_last_run(self, tmp_cache):
        wid = tmp_cache.add_watch("t", "{}")
        assert tmp_cache.record_watch_hits(wid, ["a", "b"]) == {"a", "b"}
        assert tmp_cache.record_watch_hits(wid, ["b", "c"]) == {"c"}
        w = tmp_cache.list_watches()[0]
        assert w["hit_count"] == 3
        assert w["last_run"] is not None

    def test_seen_sets_are_per_watch(self, tmp_cache):
        w1 = tmp_cache.add_watch("one", "{}")
        w2 = tmp_cache.add_watch("two", "{}")
        tmp_cache.record_watch_hits(w1, ["a"])
        assert tmp_cache.record_watch_hits(w2, ["a"]) == {"a"}

    def test_remove_drops_hits(self, tmp_cache):
        wid = tmp_cache.add_watch("t", "{}")
        tmp_cache.record_watch_hits(wid, ["a"])
        tmp_cache.remove_watch("t")
        wid2 = tmp_cache.add_watch("t", "{}")
        assert tmp_cache.record_watch_hits(wid2, ["a"]) == {"a"}

    def test_cache_clear_keeps_watches(self, tmp_cache):
        """Watches are user configuration, not cached data."""
        wid = tmp_cache.add_watch("t", "{}")
        tmp_cache.record_watch_hits(wid, ["a"])
        tmp_cache.clear()
        assert tmp_cache.get_watch("t") is not None
        assert tmp_cache.record_watch_hits(wid, ["a"]) == set()


# ── Spec ─────────────────────────────────────────────────────────────────────


class TestWatchSpec:
    def test_json_round_trip(self):
        spec = WatchSpec("q", source="arxiv", year="2020-2024", authors=["Doe"], oa_only=True)
        assert WatchSpec.from_json(spec.to_json()) == spec

    def test_from_json_ignores_unknown_keys(self):
        """Forward compatibility: a newer MOSAIC may add spec fields."""
        assert WatchSpec.from_json('{"query": "q", "future": 1}') == WatchSpec("q")

    @pytest.mark.parametrize(
        "spec",
        [
            WatchSpec(""),
            WatchSpec("q", source="nope"),
            WatchSpec("q", field="body"),
            WatchSpec("q", year="20x0"),
        ],
    )
    def test_invalid_specs_rejected(self, spec):
        with pytest.raises(ConfigError):
            spec.validate()


# ── run_watch ────────────────────────────────────────────────────────────────


class TestRunWatch:
    def test_new_means_unseen_by_this_watch_even_if_cached(self, tmp_cache, cfg):
        """The issue's "not in cache" definition would hide paper 2 here."""
        tmp_cache.save(_p(2))  # cached earlier by an unrelated search
        wid = tmp_cache.add_watch("t", "{}")
        with (
            patch("mosaic.watch.build_sources", return_value=[]),
            _search_returning([_p(1)], [_p(1), _p(2)]),
        ):
            first = run_watch("t", wid, WatchSpec("q"), cfg, tmp_cache)
            second = run_watch("t", wid, WatchSpec("q"), cfg, tmp_cache)
        assert [p.uid for p in first.new] == [_p(1).uid]
        assert [p.uid for p in second.new] == [_p(2).uid]
        assert second.total == 2

    def test_results_are_cached(self, tmp_cache, cfg):
        wid = tmp_cache.add_watch("t", "{}")
        with patch("mosaic.watch.build_sources", return_value=[]), _search_returning([_p(1)]):
            run_watch("t", wid, WatchSpec("q"), cfg, tmp_cache)
        assert tmp_cache.get_by_uid(_p(1).uid) is not None

    def test_oa_only_applied(self, tmp_cache, cfg):
        wid = tmp_cache.add_watch("t", "{}")
        papers = [_p(1, is_open_access=True), _p(2)]
        with patch("mosaic.watch.build_sources", return_value=[]), _search_returning(papers):
            run = run_watch("t", wid, WatchSpec("q", oa_only=True), cfg, tmp_cache)
        assert [p.uid for p in run.new] == [_p(1).uid]

    def test_inactive_source_raises(self, tmp_cache, cfg):
        wid = tmp_cache.add_watch("t", "{}")
        with patch("mosaic.watch.build_sources", return_value=[]):
            with pytest.raises(ConfigError, match="not active"):
                run_watch("t", wid, WatchSpec("q", source="arxiv"), cfg, tmp_cache)

    def test_filters_rebuilt_from_raw_inputs(self, tmp_cache, cfg):
        wid = tmp_cache.add_watch("t", "{}")
        with (
            patch("mosaic.watch.build_sources", return_value=[]),
            patch("mosaic.watch.search_all", return_value=[]) as sa,
        ):
            run_watch("t", wid, WatchSpec("q", year="2021-2023", authors=["Doe"]), cfg, tmp_cache)
        filters = sa.call_args.kwargs["filters"]
        assert (filters.year_from, filters.year_to, filters.authors) == (2021, 2023, ["Doe"])


# ── CLI ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def cli_env(tmp_cache, cfg):
    with (
        patch("mosaic.cli._cache_and_cfg", return_value=(tmp_cache, cfg)),
        patch("mosaic.watch.build_sources", return_value=[]),
    ):
        yield tmp_cache


class TestWatchCli:
    def test_add_records_baseline_then_run_shows_only_new(self, cli_env):
        with _search_returning([_p(1)], [_p(1), _p(2)]):
            r = runner.invoke(app, ["watch", "add", "diffusion", "--name", "dm"])
            assert r.exit_code == 0, r.output
            assert "baseline of 1 paper(s)" in r.output
            r = runner.invoke(app, ["watch", "run", "dm", "--json"])
        assert r.exit_code == 0, r.output
        out = json.loads(r.output)
        (w,) = out["watches"]
        assert w["name"] == "dm" and w["total"] == 2
        assert [p["uid"] for p in w["new"]] == [_p(2).uid]

    def test_add_duplicate_fails(self, cli_env):
        with _search_returning([], []):
            runner.invoke(app, ["watch", "add", "q", "--name", "dm"])
            r = runner.invoke(app, ["watch", "add", "q", "--name", "dm"])
        assert r.exit_code == 1
        assert "already exists" in r.output

    def test_add_invalid_year_fails_without_saving(self, cli_env):
        r = runner.invoke(app, ["watch", "add", "q", "--name", "dm", "--year", "20x0"])
        assert r.exit_code == 1
        assert cli_env.get_watch("dm") is None

    def test_add_inactive_source_rolls_back(self, cli_env):
        r = runner.invoke(app, ["watch", "add", "q", "--name", "dm", "--source", "arxiv"])
        assert r.exit_code == 1
        assert "not active" in r.output
        assert cli_env.get_watch("dm") is None

    def test_run_unknown_name_fails(self, cli_env):
        r = runner.invoke(app, ["watch", "run", "ghost"])
        assert r.exit_code == 1

    def test_run_nothing_new_message(self, cli_env):
        with _search_returning([_p(1)], [_p(1)]):
            runner.invoke(app, ["watch", "add", "q", "--name", "dm"])
            r = runner.invoke(app, ["watch", "run"])
        assert "nothing new" in r.output

    def test_run_all_json_with_no_watches(self, cli_env):
        r = runner.invoke(app, ["watch", "run", "--json"])
        assert json.loads(r.output) == {"status": "ok", "watches": []}

    def test_list_and_remove(self, cli_env):
        with _search_returning([_p(1)]):
            runner.invoke(app, ["watch", "add", "q", "--name", "dm", "--source", ""])
        r = runner.invoke(app, ["watch", "list"])
        assert "dm" in r.output
        r = runner.invoke(app, ["watch", "remove", "dm"])
        assert r.exit_code == 0
        assert cli_env.get_watch("dm") is None
        assert runner.invoke(app, ["watch", "remove", "dm"]).exit_code == 1

    def test_run_download_fetches_only_new(self, cli_env):
        with _search_returning([_p(1)], [_p(1), _p(2)]):
            runner.invoke(app, ["watch", "add", "q", "--name", "dm"])
            with patch("mosaic.cli.dl_paper", return_value="/x.pdf") as dl:
                r = runner.invoke(app, ["watch", "run", "dm", "--download", "--json"])
        assert dl.call_count == 1
        assert dl.call_args.args[0].uid == _p(2).uid
        assert json.loads(r.output)["watches"][0]["downloaded"] == 1
