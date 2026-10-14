---
pageClass: tutorial-page
aside: false
title: 10. The citation network
---

# 10. The citation network

Papers cite each other. Within your library, those citations draw a map: the papers everyone builds on, and the
groups that read each other.

## Fetching the citations

<<< @/examples/output/10/enrich.txt{console}

`--enrich-citations` asks OpenAlex, then Crossref, for the reference list of every cached paper, and keeps the
references that point to another paper in your cache. A reference to a paper you never searched for is dropped:
the map covers your library, not the literature. The citation step needs no embedding model; it runs even when
indexing fails.

With `rag.citations.enabled = true` in the [configuration file](/guide/configuration), `mosaic ask` also favours
papers that are well cited within your library ([Citation graph](/guide/citation-graph)).

## The hubs

<<< @/examples/output/10/top.txt{console}

`mosaic network` lists the papers with the most citation links inside your library, cited or citing. In a library
built from searches on one subject, these are the reviews and the founding papers.

## Clusters and a graph file

<<< @/examples/output/10/cluster.txt{console}

- `--query` starts from the cached papers matching the words and follows citations `--depth` hops out (2 by
  default).
- `--cluster` groups papers that cite each other, with Louvain community detection when the `analysis` extra
  (networkx) is installed, by connected components otherwise.
- `--output` writes the graph: `.json` for D3 or Gephi, `.dot` for Graphviz, `.md` for a Mermaid diagram that
  GitHub, Obsidian and this site render.

::: tip What you learned
`mosaic index --enrich-citations`, `mosaic network` for hubs, clusters and graph files. Guides:
[Citation graph](/guide/citation-graph), [Citation network](/guide/network); reference:
[`network`](/reference/network).
:::

The tutorial ends here. The [Cookbook](/cookbook/) has a recipe for each task, and the [Reference](/reference/)
every option.
