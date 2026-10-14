---
title: Citation Network
---

# Citation network

`mosaic network` reads the [citation graph](./citation-graph) of your cache and shows its structure: the papers
most connected to the rest of your corpus, and the groups of papers that cite each other. It can write the graph
for Gephi, D3, Graphviz or a Mermaid diagram.

## Usage

```bash
mosaic index --enrich-citations                                  # build the graph first
mosaic network --top 10                                          # the 10 most connected papers
mosaic network --query "hall thruster" --depth 1                 # papers within one citation of the matches
mosaic network --query "hall thruster" --cluster --top 3         # clusters, 3 papers shown per cluster
mosaic network --min-connections 3                               # only papers with 3 links or more
mosaic network --cluster --output graph.json                     # write the graph (and print the report)
```

Without `--cluster`, the report is one table of the `--top` papers (default 5) by degree, the number of papers in
the selection each one cites or is cited by. With `--cluster`, one table per cluster, largest first, titled after
its best-connected paper; the papers with the highest degree in the cluster are marked `Hub`.

## How it works

1. Graph. Every stored edge says "source cites target"; both ends are papers of your cache. For selection and
   clustering the direction is ignored.
2. Selection. With `--query`, the seeds are the cached papers whose title or abstract contains every word of the
   query and that have at least one edge; mosaic adds the papers within `--depth` citation hops of a seed (default 2).
   Without `--query`, the selection is the whole graph.
3. Filter. Papers with fewer than `--min-connections` links inside the selection are dropped (default 1, which drops
   papers left isolated).
4. Clusters. With `--cluster`, mosaic uses Louvain community detection from `networkx` (the `analysis` extra, with a
   fixed seed, so runs are repeatable). Without `networkx`, the clusters are the connected components.

## Output formats

The extension of `--output` picks the format:

| Extension | Format | Open with |
|---|---|---|
| `.json` | node-link JSON: `nodes` (`id`, `title`, `year`, `authors`, `citation_count`, `cluster`) and `links` (`source`, `target`) | D3, Gephi, NetworkX |
| `.gv`, `.dot` | Graphviz DOT, nodes labelled with title, first author and year | `dot -Tsvg graph.gv -o graph.svg` |
| `.md`, `.markdown` | a Mermaid `graph TD` block | GitHub, VitePress, Obsidian |

`cluster` is the cluster number, or `null` without `--cluster`.

## Limits and troubleshooting

- "No citation edges found": run `mosaic index --enrich-citations`. It needs no embedding model: when the embedding
  step fails, mosaic says so and builds the citation graph anyway.
- Few edges: an edge needs both papers in your cache. A corpus of 30 papers on one subject usually has some; papers
  gathered from unrelated searches rarely cite each other.
- "No cached papers matching ... found in the citation graph": the query matched papers, but none of them has an
  edge. Try a broader query, or enrich again after more searches.
- Mermaid diagrams of more than about a hundred nodes are hard to read; use `--min-connections` or `--query` to
  shrink the selection, or write JSON for Gephi.

See also: [tutorial chapter 10](/tutorial/10-citations), [recipes](/cookbook/ai), [`mosaic network`](/reference/network).
