"""Shared fixtures and coverage reporting hook."""

import json
import os
from pathlib import Path

import pytest

from mosaic.db import Cache
from mosaic.models import Paper

_PUBLIC = Path(__file__).parent.parent / "docs" / "public"


def pytest_sessionfinish(session, exitstatus):
    """After the test run: write coverage.json and coverage-badge.json to docs/public/.

    Skipped when coverage is off (``--no-cov`` or pytest-cov missing) or there
    is no data; the report is written to a temp file first so a failure never
    deletes or truncates the committed coverage.json.
    """
    if getattr(
        session.config.option, "no_cov", False
    ) or not session.config.pluginmanager.hasplugin("_cov"):
        return
    _PUBLIC.mkdir(parents=True, exist_ok=True)
    out = _PUBLIC / "coverage.json"
    tmp = _PUBLIC / "coverage.json.tmp"
    try:
        import coverage as coverage_lib

        cov = coverage_lib.Coverage()
        cov.load()
        if not cov.get_data().measured_files():
            return
        # Full coverage.py JSON report
        cov.json_report(outfile=str(tmp), pretty_print=True)
        # Read total percentage from the generated file
        data = json.loads(tmp.read_text())
        pct = float(data["totals"]["percent_covered_display"])
        os.replace(tmp, out)
    except Exception:
        tmp.unlink(missing_ok=True)
        return

    # Shields.io endpoint format for the badge
    if pct >= 90:
        color = "brightgreen"
    elif pct >= 75:
        color = "green"
    elif pct >= 60:
        color = "yellow"
    elif pct >= 40:
        color = "orange"
    else:
        color = "red"

    badge = {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{pct:.0f}%",
        "color": color,
    }
    (_PUBLIC / "coverage-badge.json").write_text(json.dumps(badge, indent=2))


@pytest.fixture(autouse=True)
def _isolated_user_files(tmp_path, monkeypatch):
    """Never read or write the developer's real config, cache DB or download dir.

    Code under test (e.g. the web UI config route) calls ``config.load()`` /
    ``config.save()`` directly; without this, running the suite rewrote
    ``~/.config/mosaic/config.toml`` and opened ``~/.local/share/mosaic/cache.db``.
    """
    import mosaic.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", tmp_path / "user-config" / "config.toml")
    monkeypatch.setitem(cfg_mod._DEFAULTS, "db_path", str(tmp_path / "user-data" / "cache.db"))
    monkeypatch.setitem(cfg_mod._DEFAULTS, "download_dir", str(tmp_path / "user-papers"))


@pytest.fixture
def tmp_cache(tmp_path):
    cache = Cache(str(tmp_path / "test.db"))
    yield cache
    cache.close()


@pytest.fixture
def paper():
    return Paper(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017,
        doi="10.48550/arxiv.1706.03762",
        arxiv_id="1706.03762",
        abstract="We propose the Transformer architecture.",
        journal="NeurIPS",
        pdf_url="https://arxiv.org/pdf/1706.03762",
        source="arXiv",
        is_open_access=True,
    )


@pytest.fixture
def paper_with_openalex_id():
    """Paper that already has a stored OpenAlex W-ID."""
    return Paper(
        title="BERT: Pre-training of Deep Bidirectional Transformers",
        authors=["Jacob Devlin", "Ming-Wei Chang"],
        year=2019,
        doi="10.18653/v1/n19-1423",
        abstract="We introduce BERT.",
        source="OpenAlex",
        openalex_id="W2963403868",
    )


@pytest.fixture
def tmp_cache_with_citations(tmp_path):
    """Cache pre-populated with two papers and one citation edge between them."""
    cache = Cache(str(tmp_path / "test_citations.db"))
    p1 = Paper(title="Paper A", doi="10.9999/a", source="test", year=2020, abstract="abstract a")
    p2 = Paper(title="Paper B", doi="10.9999/b", source="test", year=2021, abstract="abstract b")
    cache.save(p1)
    cache.save(p2)
    cache.upsert_citation_edges([(p1.uid, p2.uid, "openalex")])
    return cache, p1, p2


def make_response(text="", json_data=None, status_code=200):
    """Build a minimal mock httpx response."""
    from unittest.mock import MagicMock

    m = MagicMock()
    m.status_code = status_code
    m.text = text
    if json_data is not None:
        m.json.return_value = json_data
    m.raise_for_status = MagicMock()
    return m
