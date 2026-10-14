"""Saved searches with change detection (``mosaic watch``, issue #17).

A watch stores the user's *raw* search inputs, not a serialised
``SearchFilters``: every run rebuilds filters through ``build_filters``, so a
watch validates and behaves exactly like the equivalent ``mosaic search``.

Each watch keeps its own seen-set of paper uids (``watch_hits``). A paper is
"new" when this watch has never returned it, regardless of whether it is
already in the cache from some other search.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from mosaic.db import Cache
from mosaic.errors import ConfigError
from mosaic.models import Paper
from mosaic.search import search_all
from mosaic.services import build_filters, filter_papers
from mosaic.source_registry import SRC_MAP, build_sources

log = logging.getLogger(__name__)


@dataclass
class WatchSpec:
    """The search a watch re-runs; mirrors the ``mosaic search`` options."""

    query: str
    source: str = ""  # source shorthand (``SRC_MAP`` key); empty = all enabled
    max_results: int = 25
    year: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    field: str = "all"
    raw_query: str = ""
    oa_only: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> WatchSpec:
        data = json.loads(raw)
        known = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in known})

    def validate(self) -> None:
        """Raise ConfigError if the spec could never run."""
        if not self.query.strip() and not self.raw_query:
            raise ConfigError("A watch needs a query.")
        if self.source and self.source.lower() not in SRC_MAP:
            raise ConfigError(f"Unknown source '{self.source}'. Use: {', '.join(SRC_MAP)}")
        if self.field not in ("all", "title", "abstract"):
            raise ConfigError('field must be "title", "abstract", or "all"')
        _, warning = build_filters(year=self.year)
        if warning:
            raise ConfigError(warning)


@dataclass
class WatchRun:
    """Outcome of running one watch."""

    name: str
    query: str
    new: list[Paper]
    total: int
    errors: list[str]


def run_watch(name: str, watch_id: int, spec: WatchSpec, cfg: dict, cache: Cache) -> WatchRun:
    """Run *spec* now, cache every result, and return the papers new to this watch.

    Raises
    ------
    ConfigError
        If the spec's source is not active in the current config.
    """
    sources = build_sources(cfg)
    if spec.source:
        wanted = SRC_MAP[spec.source.lower()]
        sources = [s for s in sources if s.name == wanted]
        if not sources:
            raise ConfigError(
                f"Source '{spec.source}' is not active (missing API key or disabled in config)."
            )

    filters, _ = build_filters(
        year=spec.year,
        author=spec.authors,
        journal=spec.journal,
        field=spec.field,
        raw_query=spec.raw_query,
    )
    errors: list[str] = []
    papers = search_all(
        sources, spec.query, max_per_source=spec.max_results, filters=filters, errors=errors
    )
    papers = filter_papers(papers, oa_only=spec.oa_only)

    for p in papers:
        cache.save(p)
    new_uids = cache.record_watch_hits(watch_id, [p.uid for p in papers])
    new = [p for p in papers if p.uid in new_uids]
    log.info("watch %s: %d result(s), %d new", name, len(papers), len(new))
    return WatchRun(name=name, query=spec.query, new=new, total=len(papers), errors=errors)
