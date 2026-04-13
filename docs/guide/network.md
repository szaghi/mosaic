---
title: Citation Network
---

# Citation Network (`mosaic network`)

`mosaic network` turns the local citation graph into a topology-based research intelligence tool.  After enriching your cache with citation edges (`mosaic index --enrich-citations`), you can explore how papers connect to each other, identify the most central works, and cluster your corpus into topic communities — all without leaving the terminal.

## Quickstart

```bash
# 1. Build a citation graph for your cached papers
mosaic index --enrich-citations

# 2. Show the most-connected papers in the full graph
mosaic network --top 10

# 3. Explore papers related to a topic (2-hop BFS from matching seed papers)
mosaic network --query "transformer attention" --depth 2

# 4. Group papers into clusters and show hubs
mosaic network --query "protein folding" --cluster --top 5

# 5. Export for downstream tools
mosaic network --output graph.json          # D3.js / Gephi / NetworkX
mosaic network --output graph.gv            # Graphviz DOT (dot -Tpng graph.gv -o graph.png)
mosaic network --output graph.md            # Mermaid diagram (embedded in Markdown)
```

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--query TEXT` | `-q` | | Seed the graph from papers matching this query in the cache |
| `--depth INT` | | `2` | Number of citation hops to follow from seed papers |
| `--min-connections INT` | | `1` | Exclude papers with fewer edges than this |
| `--cluster` | | off | Group papers into topic clusters |
| `--output FILE` | `-o` | | Write graph to file (extension determines format) |
| `--top INT` | | `5` | Most-connected papers to show per cluster in the terminal |

## How it works

### Graph construction

All `(source, target)` citation edges stored in the local `paper_citations` table are loaded into an in-memory adjacency list.  The graph is **directed** internally (edge = "source cites target") but treated as **undirected** for traversal and clustering.

### Subgraph selection

When `--query` is given, MOSAIC performs a BFS from the matching seed papers up to `--depth` hops and restricts all subsequent analysis to the resulting subgraph.  Without `--query`, the full citation graph is analysed.

### Minimum-connections filter

Papers with fewer than `--min-connections` undirected edges (after subgraph selection) are removed.  The default value of `1` excludes completely isolated papers that have no citation link to any other cached paper.

### Clustering (`--cluster`)

When `--cluster` is passed, MOSAIC groups papers into communities:

1. **Louvain community detection** via `networkx` (install with `pip install 'mosaic-search[analysis]'`) — identifies dense sub-graphs with high internal connectivity.
2. **Fallback: connected components** — used automatically when `networkx` is not installed.

The terminal report labels the highest-degree paper in each cluster as **Hub**.

### Terminal output

Without `--cluster`, the top-N most-connected papers are shown in a ranked table.

With `--cluster`, a separate table is printed per cluster, sorted by degree descending:

```
── Cluster 1 — Attention Is All You Need (8 papers) ─────────────────────
 Hub  Attention Is All You Need          Vaswani et al.   2017  degree=6
 Hub  BERT: Pre-training of Deep…        Devlin et al.    2019  degree=6
      Efficient Transformers: Survey     Tay et al.       2020  degree=3
      …

── Cluster 2 — Denoising Diffusion Probabilistic… (5 papers) ─────────────
 Hub  DDPM                               Ho et al.        2020  degree=4
      Stable Diffusion                   Rombach et al.   2022  degree=2
      …
```

## Output formats

| Extension | Format | Use case |
|-----------|--------|----------|
| `.json` | Node-link JSON | D3.js, Gephi, NetworkX |
| `.gv` / `.dot` | Graphviz DOT | `dot -Tpng graph.gv -o graph.png` |
| `.md` | Mermaid diagram | VitePress, GitHub README, Obsidian |

### JSON schema

```json
{
  "nodes": [
    {
      "id": "doi:10.48550/arxiv.1706.03762",
      "title": "Attention Is All You Need",
      "year": 2017,
      "authors": "Vaswani et al.",
      "citation_count": 85000,
      "cluster": 0
    }
  ],
  "links": [
    { "source": "doi:10.48550/...", "target": "doi:10.18653/..." }
  ]
}
```

The `cluster` field is `null` when `--cluster` is not used.

## Prerequisites

Citation edges must be present in the local cache.  If none are found, `mosaic network` exits with a hint:

```
No citation edges found. Run mosaic index --enrich-citations first.
```

See the [Citation Graph](./citation-graph) guide for how to build and configure the citation graph.

## Optional dependency

Louvain clustering requires `networkx`:

```bash
pip install 'mosaic-search[analysis]'
# or with pipx:
pipx inject mosaic-search networkx
```

Without it, `--cluster` falls back to connected-components (no change in the interface).

## Workflow example

```bash
# Collect 50 papers on graph neural networks
mosaic search "graph neural networks" -n 50

# Index for RAG and enrich citations
mosaic index --enrich-citations

# Explore the topic cluster
mosaic network --query "graph neural networks" --cluster --top 5

# Export for a presentation
mosaic network --query "graph neural networks" --cluster --output gnn-network.md
```
