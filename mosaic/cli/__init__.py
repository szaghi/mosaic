"""MOSAIC CLI — Multi-source Scientific Article Indexer and Collector.

Commands live in one module per area; importing a module registers its
commands on :data:`app`.  The import order below is the order commands are
registered in.
"""

from mosaic.cli.app import app

# isort: off
from mosaic.cli import search, rag, settings, skill, notebook, analysis, ui, auth, cache  # noqa: F401

# isort: on

__all__ = ["app"]
