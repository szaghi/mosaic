"""LLM response parsing (ranking, compare), graph export escaping, Obsidian collisions."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

import pytest

from mosaic.compare import _parse_obj_list, compare_papers
from mosaic.models import Paper
from mosaic.network import to_dot, to_mermaid
from mosaic.obsidian import ObsidianVault
from mosaic.ranking import _parse_float_list, strip_code_fences

# ── code fences / clamping ────────────────────────────────────────────────────


class TestStripCodeFences:
    def test_json_fence(self):
        assert strip_code_fences("```json\n[0.1, 0.2]\n```") == "[0.1, 0.2]"

    def test_bare_fence_with_prose(self):
        assert strip_code_fences('Here you go:\n```\n{"a": 1}\n```\nThanks') == '{"a": 1}'

    def test_no_fence(self):
        assert strip_code_fences("  [1]  ") == "[1]"


class TestRankingParse:
    def test_fenced_json_accepted(self):
        assert _parse_float_list("```json\n[0.9, 0.1]\n```", 2) == [0.9, 0.1]

    def test_scores_clamped(self):
        assert _parse_float_list("[7, -2, 0.5]", 3) == [1.0, 0.0, 0.5]

    def test_nan_becomes_neutral(self):
        assert _parse_float_list('{"scores": [NaN, 0.2]}', 2) == [0.5, 0.2]


# ── compare ───────────────────────────────────────────────────────────────────


def _papers(n: int) -> list[Paper]:
    return [Paper(title=f"P{i}", year=2000 + i, source="arXiv") for i in range(n)]


class TestCompareParse:
    def test_fenced_json_accepted(self):
        rows = _parse_obj_list('```json\n[{"method": "CNN"}]\n```', 1, ["method"])
        assert rows == [{"method": "CNN"}]


class TestComparePerBatchFallback:
    _CFG: ClassVar[dict] = {"llm": {"provider": "openai", "api_key": "k"}}

    def test_one_failing_batch_keeps_the_others(self):
        papers = _papers(25)  # two batches: 20 + 5
        good = "[" + ",".join('{"method": "M"}' for _ in range(20)) + "]"

        calls = {"n": 0}

        def fake_llm(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return good
            raise RuntimeError("HTTP 429")

        errors: list[str] = []
        with patch("mosaic.compare._call_llm", side_effect=fake_llm):
            rows = compare_papers(papers, ["method", "year"], self._CFG, errors=errors)
        assert len(rows) == 25
        assert all(r["method"] == "M" for r in rows[:20])
        assert all(r["method"] == "–" for r in rows[20:])
        assert rows[24]["year"] == "2024"  # metadata still filled for the failed batch
        assert len(errors) == 1 and "21–25" in errors[0] and "429" in errors[0]

    def test_unparseable_batch_reported(self):
        errors: list[str] = []
        with patch("mosaic.compare._call_llm", return_value="Sorry, I can't do that."):
            rows = compare_papers(_papers(2), ["method"], self._CFG, errors=errors)
        assert rows == [{"method": "–"}, {"method": "–"}]
        assert errors and "non-JSON" in errors[0]

    def test_errors_kwarg_optional(self):
        with patch("mosaic.compare._call_llm", side_effect=RuntimeError("boom")):
            rows = compare_papers(_papers(1), ["method"], self._CFG)
        assert rows == [{"method": "–"}]


# ── network exports ───────────────────────────────────────────────────────────


def _net(uids_titles: dict[str, str]):
    papers = {uid: Paper(title=t, doi=uid.removeprefix("doi:")) for uid, t in uids_titles.items()}
    uids = list(uids_titles)
    adj = {uids[0]: uids[1:]}
    return set(uids), adj, papers


class TestMermaidExport:
    def test_ids_unique_for_colliding_uids(self):
        nodes, adj, papers = _net({"doi:10.1/a.b": "One", "doi:10.1/a_b": "Two"})
        out = to_mermaid(nodes, adj, papers)
        node_ids = re.findall(r"^\s+(\w+)\[", out, re.MULTILINE)
        assert len(node_ids) == 2 and len(set(node_ids)) == 2
        assert re.search(r"^\s+n0 --- n1$", out, re.MULTILINE)

    def test_sici_doi_and_quotes_are_syntax_safe(self):
        nodes, adj, papers = _net(
            {"doi:10.1002/(sici)1097<3::aid>;2-x": 'Say "hi" <b>', "doi:10.1/b": "B"}
        )
        out = to_mermaid(nodes, adj, papers)
        for line in out.splitlines()[2:-1]:
            ident = line.strip().split("[", 1)[0].split(" ", 1)[0]
            assert re.fullmatch(r"n\d+", ident)
        assert "#quot;hi#quot;" in out and "#lt;b#gt;" in out


class TestDotExport:
    def test_backslash_and_quote_escaped(self):
        nodes, adj, papers = _net({"doi:10.1/a": 'M{\\"o}bius "strip"', "doi:10.1/b": "B"})
        out = to_dot(nodes, adj, papers)
        label_line = next(
            line for line in out.splitlines() if "doi:10.1/a" in line and "label" in line
        )
        label = label_line.split('label="', 1)[1].rsplit('"];', 1)[0]
        # Every quote inside the label is escaped; backslashes are doubled
        assert re.search(r'(?<!\\)"', label) is None
        assert 'M{\\\\\\"o}bius \\"strip\\"' in label
        assert "\\n" in label  # DOT line break kept


# ── Obsidian collisions ───────────────────────────────────────────────────────

_TITLE = "A survey of deep learning methods for medical image segmentation tasks"


def _colliding():
    a = Paper(title=_TITLE, authors=["Wei Zhang"], year=2020, doi="10.1/a", source="arXiv")
    b = Paper(title=_TITLE, authors=["Wei Li"], year=2020, doi="10.1/b", source="arXiv")
    return a, b


class TestObsidianCollisions:
    def test_different_paper_gets_suffixed_note(self, tmp_path):
        v = ObsidianVault(tmp_path, subfolder="")
        a, b = _colliding()
        assert v.export_papers([a]) == (1, 0)
        assert v.export_papers([b]) == (1, 0)
        notes = sorted(p.name for p in tmp_path.glob("*.md"))
        assert len(notes) == 2
        assert "doi: 10.1/b" in v.note_path(b).read_text()
        assert "doi: 10.1/a" in v.note_path(a).read_text()

    def test_same_paper_reexport_is_skipped(self, tmp_path):
        v = ObsidianVault(tmp_path, subfolder="")
        a, b = _colliding()
        v.export_papers([a, b])
        assert v.export_papers([a, b]) == (0, 2)

    def test_user_note_with_same_name_is_not_clobbered(self, tmp_path):
        v = ObsidianVault(tmp_path, subfolder="")
        p = Paper(title="Attention", authors=["Ashish Vaswani"], year=2017, source="arXiv")
        own = tmp_path / f"{v.note_stem(p)}.md"
        own.write_text("my own thoughts")
        assert v.export_papers([p]) == (1, 0)
        assert own.read_text() == "my own thoughts"
        assert v.note_path(p) != own

    def test_in_batch_collision_wikilinks_point_at_real_files(self, tmp_path):
        v = ObsidianVault(tmp_path, subfolder="", wikilinks=True)
        a, b = _colliding()
        v.export_papers([a, b])
        link = re.search(r"\[\[(.+?)\]\]", v.note_path(a).read_text()).group(1)
        assert link == v.note_path(b).stem
        assert (tmp_path / f"{link}.md").exists()


# ── conftest coverage hook ────────────────────────────────────────────────────


class TestCoverageHook:
    def test_no_cov_leaves_public_dir_untouched(self, tmp_path):
        from tests import conftest

        session = SimpleNamespace(
            config=SimpleNamespace(
                option=SimpleNamespace(no_cov=True),
                pluginmanager=SimpleNamespace(hasplugin=lambda name: True),
            )
        )
        with patch.object(conftest, "_PUBLIC", tmp_path / "public"):
            conftest.pytest_sessionfinish(session, 0)
        assert not (tmp_path / "public").exists()

    def test_missing_cov_plugin_leaves_public_dir_untouched(self, tmp_path):
        from tests import conftest

        session = SimpleNamespace(
            config=SimpleNamespace(
                option=SimpleNamespace(),
                pluginmanager=SimpleNamespace(hasplugin=lambda name: False),
            )
        )
        with patch.object(conftest, "_PUBLIC", tmp_path / "public"):
            conftest.pytest_sessionfinish(session, 0)
        assert not (tmp_path / "public").exists()


@pytest.mark.parametrize("n", [0, 1])
def test_compare_without_llm_uses_metadata(n):
    rows = compare_papers(_papers(n), ["year"], {"llm": {}})
    assert len(rows) == n
