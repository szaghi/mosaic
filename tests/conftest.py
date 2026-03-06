"""Shared fixtures and coverage reporting hook."""
import json
from pathlib import Path
import pytest
from mosaic.db import Cache
from mosaic.models import Paper

_PUBLIC = Path(__file__).parent.parent / "docs" / "public"


def pytest_sessionfinish(session, exitstatus):
    """After the test run: write coverage.json and coverage-badge.json to docs/public/."""
    _PUBLIC.mkdir(parents=True, exist_ok=True)
    try:
        import coverage as coverage_lib
        cov = coverage_lib.Coverage()
        cov.load()
        # Full coverage.py JSON report
        cov.json_report(outfile=str(_PUBLIC / "coverage.json"), pretty_print=True)
        # Read total percentage from the generated file
        data = json.loads((_PUBLIC / "coverage.json").read_text())
        pct = float(data["totals"]["percent_covered_display"])
    except Exception:
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


@pytest.fixture
def tmp_cache(tmp_path):
    return Cache(str(tmp_path / "test.db"))


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
