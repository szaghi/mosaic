---
title: Citation Graph
---

# Citation Graph

MOSAIC can enrich its local RAG pipeline with a **citation graph** — a network of bibliographic relationships stored alongside your paper embeddings. Papers that share citation edges with other retrieved results are promoted in the ranking, improving retrieval precision without requiring an LLM at index time.

## How it works

The citation graph adds a second signal to the retrieval step:

1. **Enrich**: for each cached paper, mosaic fetches its outgoing reference list from OpenAlex (or CrossRef as fallback) and stores the edges in a local `paper_citations` table. Only edges whose target paper is already in your local cache are stored — dangling references to uncached papers are dropped.

2. **Boost**: when `rag.citations.enabled = true`, the retrieval step combines cosine similarity rank with citation link count:

   ```
   score(paper) = (1 / rank) × (1 + α × citation_links(paper, result_set))
   ```

   Papers with more citation edges to/from other retrieved papers rise in rank. When `α = 0` the original cosine order is preserved.

3. **Expand** *(optional)*: with `expand_neighbors = true`, 1-hop citation neighbors of the top results are added to the candidate pool before final ranking, widening recall for closely related papers not caught by embeddings alone.

## Quickstart

```bash
# 1. Index your papers (embed title + abstract)
mosaic index

# 2. Enrich the citation graph
mosaic index --enrich-citations

# 3. Enable citation boosting in config
mosaic config --set rag.citations.enabled=true

# 4. Ask a question — retrieval now uses the citation graph
mosaic ask "What are the main approaches to neural machine translation?"
```

## Provider coverage

Citation edges are fetched in priority order. The first provider that returns a non-empty reference list wins; subsequent providers are skipped for that paper.

| Provider | Coverage | Auth required | Notes |
|----------|----------|---------------|-------|
| **OpenAlex** | ~90 %+ of DOI/arXiv papers | None (polite pool) | Primary source; handles DOI, arXiv ID, and stored W-IDs |
| **CrossRef** | Varies by publisher | None (polite pool) | Supplementary; many publishers do not deposit reference lists |
| **OpenCitations** | OA literature | None | Tertiary; skews toward open-access journals |

::: tip Polite pool
Set `unpaywall.email` in your config to identify your requests to OpenAlex and CrossRef. This opts you into their "polite pool" for better rate limits:

```bash
mosaic config --unpaywall-email you@example.com
```
:::

## Configuration

All citation graph settings live under `[rag.citations]` in `~/.config/mosaic/config.toml`:

```toml
[rag.citations]
enabled          = false              # apply graph boosting in retrieve()
boost_alpha      = 0.3               # citation weight; 0 = pure cosine
providers        = ["openalex", "crossref"]  # priority order
expand_neighbors = false             # add 1-hop neighbors to candidate pool
```

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Master switch for citation boosting during `mosaic ask` / `mosaic chat` |
| `boost_alpha` | `0.3` | Re-scoring weight. Higher values give more weight to citation links; `0` disables boosting while keeping the graph populated |
| `providers` | `["openalex","crossref"]` | Ordered provider list. Valid values: `"openalex"`, `"crossref"`, `"opencitations"` |
| `expand_neighbors` | `false` | When true, citation neighbors of top-*k* results are appended to the candidate pool before final ranking |

### Auto-enrichment

Set `enabled = true` to trigger enrichment automatically every time you run `mosaic index`, without needing the `--enrich-citations` flag:

```toml
[rag.citations]
enabled = true
```

## Related commands

Once you have citation edges stored, you can use two additional commands built on top of the graph:

- **`mosaic network`** — explore topology, identify hubs, cluster into communities, and export to JSON/DOT/Mermaid.  See the [Citation Network](./network) guide.
- **`mosaic compare`** — generate a structured comparison table across a set of papers using an LLM.  See the [Compare Papers](./compare) guide.

## CLI reference

### `mosaic index --enrich-citations`

Embeds papers and then fetches citation edges for all candidates:

```bash
mosaic index --enrich-citations
mosaic index --reindex --enrich-citations   # re-embed AND re-enrich
```

The enrichment step is idempotent: papers already present in `paper_citations` are skipped on subsequent runs (unless `--reindex` is passed).

## Tuning `boost_alpha`

The right value depends on your corpus:

| Corpus type | Suggested α |
|-------------|-------------|
| Tightly scoped (single subfield) | `0.4–0.6` — citations are highly informative |
| Broad interdisciplinary | `0.1–0.2` — citation links are noisier |
| Mostly preprints (no DOIs) | `0.0` — few edges available; keep cosine-only |

Start with the default `0.3` and adjust based on whether `mosaic ask` surfaces the right papers.

## Limitations

- **Papers without DOI or arXiv ID** (title-slug UIDs) cannot be enriched — they have no identifier that citation databases can resolve. They remain retrievable via cosine similarity; only the boosting signal is absent.
- **Papers not in OpenAlex** — rare for peer-reviewed literature but common for very new preprints or niche repositories. CrossRef provides a fallback for DOI-bearing papers.
- **CrossRef coverage is uneven** — some publishers do not deposit reference lists to CrossRef. If CrossRef returns nothing for a well-known paper, this is expected behaviour.
- **Re-enrichment of missed papers** — papers queried during enrichment that had no local citation matches are not tracked as "enriched" and will be re-attempted on the next run. This is a known limitation; a future release will add explicit attempt tracking.

## Adding a custom provider

Implement `BaseCitationProvider` from `mosaic.citations.base`, register the class name in `mosaic/citations/registry.py`, then add it to `rag.citations.providers` in your config:

```python
# mosaic/citations/myprovider.py
from mosaic.citations.base import BaseCitationProvider
from mosaic.models import Paper

class MyProvider(BaseCitationProvider):
    name = "myprovider"

    def can_handle(self, paper: Paper) -> bool:
        return bool(paper.doi)

    def fetch_references(self, paper: Paper) -> list[str]:
        # Return list of "doi:…" or "arxiv:…" UID strings
        ...
```

```python
# In mosaic/citations/registry.py — add to _REGISTRY:
"myprovider": MyProvider,
```

```toml
# In config.toml:
[rag.citations]
providers = ["openalex", "myprovider"]
```
