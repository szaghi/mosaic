---
title: Citation Graph
---

# Citation graph

mosaic can record who cites whom among the papers in your cache. The edges feed [`mosaic network`](./network) (hubs
and clusters of your corpus) and, if you enable it, the retrieval of [`mosaic ask` and `mosaic chat`](./rag), where
papers linked by citations to the other retrieved papers move up.

## Usage

```bash
mosaic index --enrich-citations            # embed new papers, then fetch their reference lists
mosaic index --reindex --enrich-citations  # re-embed everything and re-fetch every reference list
mosaic network --top 10                    # use the graph
```

Enrichment is part of `mosaic index`, after the embedding step, but does not depend on it: without an embedding
model, `mosaic index --enrich-citations` reports the embedding error and builds the graph anyway.

## How it works

Enrich. For each cached paper, mosaic asks the providers in order for its reference list and keeps only the
references that are papers in your cache: a reference to a paper you have never searched for is dropped. The first
provider that yields at least one such edge wins for that paper. Edges go into the `paper_citations` table of the
cache database, as "source cites target", tagged with the provider.

| Provider | Handles | Notes |
|---|---|---|
| `openalex` | papers with a DOI, an arXiv ID or an OpenAlex ID | first by default |
| `crossref` | papers with a DOI | publishers deposit reference lists unevenly |
| `opencitations` | papers with a DOI | the COCI index; off unless you list it |

Papers with neither a DOI nor an arXiv ID cannot be enriched. A paper that already has edges is skipped on later
runs (unless `--reindex`); a paper whose references matched nothing in your cache is queried again on every run.
OpenAlex and Crossref receive `unpaywall.email` (or `sources.openalex.email`) to put your requests in their polite
pool.

Because edges only connect papers you have, the graph grows with your cache: search more, then enrich again.

Boost. With `rag.citations.enabled = true`, retrieval re-ranks the nearest papers by

```
score(i) = (1 / i) * (1 + boost_alpha * links(i))
```

where i is the paper's rank by vector distance and links(i) counts the citation edges, in either direction, between
the paper and the other retrieved papers. `boost_alpha = 0` keeps the vector order. With `expand_neighbors = true`,
the cached papers cited by the top results are appended after them; they only reach the answer when fewer than
`top_k` papers were retrieved.

## Configuration

`mosaic config` has no flags for these keys: edit `~/.config/mosaic/config.toml`.

```toml
[rag.citations]
enabled          = false                    # boost retrieval, and enrich on every mosaic index
boost_alpha      = 0.3                      # weight of citation links; 0 = vector order
providers        = ["openalex", "crossref"] # tried in this order; "opencitations" also exists
expand_neighbors = false                    # append cited papers to the retrieved ones
```

With `enabled = true`, every `mosaic index` also enriches, without `--enrich-citations`.

A value of `boost_alpha` between 0.4 and 0.6 suits a corpus on one narrow subject, where citations are informative;
between 0.1 and 0.2 a broad one. Start from 0.3 and compare the answers of `mosaic ask --show-sources`.

## Adding a provider

Subclass `BaseCitationProvider` (`mosaic/citations/base.py`): give it a `name`, a `can_handle(paper)` and a
`fetch_references(paper)` that returns UIDs such as `doi:10.1063/1.4972269` or `arxiv:2304.06563`. Register the
class in `_REGISTRY` of `mosaic/citations/registry.py` and add its name to `providers`.

See also: [tutorial chapter 10](/tutorial/10-citations), [recipes](/cookbook/ai), [`mosaic index`](/reference/index-command),
[citation network](./network).
