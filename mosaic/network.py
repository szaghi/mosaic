"""Citation network analysis: BFS traversal, clustering, and multi-format export."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from mosaic.models import Paper

_log = logging.getLogger(__name__)


# ── Graph construction ────────────────────────────────────────────────────────


def build_adj(edges: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Build a directed adjacency list from (source_uid, target_uid) pairs.

    Args:
        edges: Pairs of citation edges, each ``(source, target)``.

    Returns:
        Dict mapping each UID to the list of UIDs it cites.  Every UID that
        appears as a target is also present as a key (with an empty list if it
        has no outgoing edges itself).
    """
    adj: dict[str, list[str]] = defaultdict(list)
    for src, tgt in edges:
        adj[src].append(tgt)
        if tgt not in adj:
            adj[tgt] = []
    return dict(adj)


def _undirected(adj: dict[str, list[str]], nodes: set[str] | None = None) -> dict[str, set[str]]:
    """Return an undirected neighbour set, optionally restricted to *nodes*."""
    undir: dict[str, set[str]] = defaultdict(set)
    for src, targets in adj.items():
        for tgt in targets:
            if nodes is None or (src in nodes and tgt in nodes):
                undir[src].add(tgt)
                undir[tgt].add(src)
    return dict(undir)


def subgraph_from_seeds(
    adj: dict[str, list[str]],
    seeds: list[str],
    depth: int,
) -> set[str]:
    """BFS from *seeds* up to *depth* hops on an undirected view of *adj*.

    Args:
        adj: Directed adjacency list (as returned by :func:`build_adj`).
        seeds: Starting UIDs.  UIDs not present in *adj* are silently ignored.
        depth: Maximum number of hops to follow.

    Returns:
        Set of all UIDs reachable within *depth* hops, including the seeds.
    """
    undir = _undirected(adj)
    visited: set[str] = {uid for uid in seeds if uid in adj}
    frontier = visited.copy()
    for _ in range(depth):
        next_frontier: set[str] = set()
        for uid in frontier:
            for nbr in undir.get(uid, set()):
                if nbr not in visited:
                    visited.add(nbr)
                    next_frontier.add(nbr)
        frontier = next_frontier
        if not frontier:
            break
    return visited


def compute_degree(adj: dict[str, list[str]], nodes: set[str]) -> dict[str, int]:
    """Compute the undirected degree of each node within *nodes*.

    Args:
        adj: Directed adjacency list.
        nodes: Subgraph to restrict the count to.

    Returns:
        Dict mapping each uid in *nodes* to its undirected edge count.
    """
    undir = _undirected(adj, nodes)
    return {n: len(undir.get(n, set())) for n in nodes}


def count_edges(nodes: set[str], adj: dict[str, list[str]]) -> int:
    """Count undirected edges within *nodes*."""
    edge_set: set[tuple[str, str]] = set()
    for src, targets in adj.items():
        if src in nodes:
            for tgt in targets:
                if tgt in nodes:
                    a, b = (src, tgt) if src <= tgt else (tgt, src)
                    edge_set.add((a, b))
    return len(edge_set)


# ── Clustering ────────────────────────────────────────────────────────────────


def connected_components(nodes: set[str], adj: dict[str, list[str]]) -> list[set[str]]:
    """Return connected components (undirected) among *nodes*, largest first.

    Args:
        nodes: Subgraph of interest.
        adj: Directed adjacency list.

    Returns:
        List of node sets, one per component, sorted by size descending.
    """
    undir = _undirected(adj, nodes)
    visited: set[str] = set()
    components: list[set[str]] = []
    for node in nodes:
        if node in visited:
            continue
        comp: set[str] = set()
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp.add(cur)
            for nbr in undir.get(cur, set()):
                if nbr in nodes and nbr not in visited:
                    stack.append(nbr)
        components.append(comp)
    components.sort(key=len, reverse=True)
    return components


def louvain_clusters(nodes: set[str], adj: dict[str, list[str]]) -> list[set[str]]:
    """Louvain community detection via networkx; falls back to connected components.

    Args:
        nodes: Subgraph of interest.
        adj: Directed adjacency list.

    Returns:
        List of node sets (communities), sorted by size descending.
        Falls back to :func:`connected_components` when networkx is not installed.
    """
    try:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities

        g: nx.Graph = nx.Graph()
        g.add_nodes_from(nodes)
        undir = _undirected(adj, nodes)
        for node in nodes:
            for nbr in undir.get(node, set()):
                g.add_edge(node, nbr)

        parts = louvain_communities(g, seed=42)
        result = [c & nodes for c in parts if c & nodes]
        result.sort(key=len, reverse=True)
        return result
    except ImportError:
        _log.debug("networkx not available — falling back to connected_components")
        return connected_components(nodes, adj)


# ── Export serializers ────────────────────────────────────────────────────────


def _cluster_map(clusters: list[set[str]]) -> dict[str, int]:
    return {uid: i for i, comp in enumerate(clusters) for uid in comp}


def to_json(
    nodes: set[str],
    adj: dict[str, list[str]],
    papers: dict[str, Paper],
    clusters: list[set[str]] | None = None,
) -> str:
    """Node-link JSON compatible with D3.js, Gephi, and NetworkX.

    Args:
        nodes: UIDs to include in the export.
        adj: Directed adjacency list.
        papers: UID to Paper lookup for metadata.
        clusters: Optional cluster assignments.

    Returns:
        JSON string with ``"nodes"`` and ``"links"`` keys.
    """
    cm = _cluster_map(clusters) if clusters else {}
    node_list = [
        {
            "id": uid,
            "title": papers[uid].title if uid in papers else uid,
            "year": papers[uid].year if uid in papers else None,
            "authors": papers[uid].short_authors if uid in papers else "",
            "citation_count": papers[uid].citation_count if uid in papers else None,
            "cluster": cm.get(uid),
        }
        for uid in sorted(nodes)
    ]
    edge_set: set[tuple[str, str]] = set()
    for src, targets in adj.items():
        if src in nodes:
            for tgt in targets:
                if tgt in nodes:
                    a, b = (src, tgt) if src <= tgt else (tgt, src)
                    edge_set.add((a, b))
    links = [{"source": a, "target": b} for a, b in sorted(edge_set)]
    return json.dumps({"nodes": node_list, "links": links}, indent=2, ensure_ascii=False)


def to_dot(
    nodes: set[str],
    adj: dict[str, list[str]],
    papers: dict[str, Paper],
) -> str:
    """Graphviz DOT format (undirected graph).

    Args:
        nodes: UIDs to include.
        adj: Directed adjacency list.
        papers: UID to Paper lookup.

    Returns:
        DOT-format string suitable for ``dot -Tpng``.
    """
    lines = ["graph G {", "  graph [overlap=false];"]
    for uid in sorted(nodes):
        p = papers.get(uid)
        if p:
            snippet = p.title if len(p.title) <= 45 else p.title[:44] + "…"
            raw_label = f"{snippet}\\n{p.short_authors} {p.year or ''}"
        else:
            raw_label = uid
        label = raw_label.replace('"', '\\"')
        lines.append(f'  "{uid}" [label="{label}"];')

    edge_set: set[tuple[str, str]] = set()
    for src, targets in adj.items():
        if src in nodes:
            for tgt in targets:
                if tgt in nodes:
                    a, b = (src, tgt) if src <= tgt else (tgt, src)
                    edge_set.add((a, b))
    for a, b in sorted(edge_set):
        lines.append(f'  "{a}" -- "{b}";')
    lines.append("}")
    return "\n".join(lines)


def to_mermaid(
    nodes: set[str],
    adj: dict[str, list[str]],
    papers: dict[str, Paper],
) -> str:
    """Mermaid diagram embedded in a Markdown fenced code block.

    Args:
        nodes: UIDs to include.
        adj: Directed adjacency list.
        papers: UID to Paper lookup.

    Returns:
        Markdown string with a ``mermaid`` fenced code block.
    """

    def safe(uid: str) -> str:
        return uid.replace(":", "_").replace("/", "_").replace(".", "_").replace("-", "_")

    lines = ["```mermaid", "graph TD"]
    for uid in sorted(nodes):
        p = papers.get(uid)
        if p:
            label = (p.title[:40] + "…") if len(p.title) > 40 else p.title
        else:
            label = uid
        label = label.replace('"', "'")
        lines.append(f'  {safe(uid)}["{label}"]')

    edge_set: set[tuple[str, str]] = set()
    for src, targets in adj.items():
        if src in nodes:
            for tgt in targets:
                if tgt in nodes:
                    a, b = (src, tgt) if src <= tgt else (tgt, src)
                    edge_set.add((a, b))
    for a, b in sorted(edge_set):
        lines.append(f"  {safe(a)} --- {safe(b)}")
    lines.append("```")
    return "\n".join(lines)


def export_graph(
    nodes: set[str],
    adj: dict[str, list[str]],
    papers: dict[str, Paper],
    path: Path,
    clusters: list[set[str]] | None = None,
) -> None:
    """Write the graph to *path* in a format determined by the file extension.

    Args:
        nodes: UIDs to include in the export.
        adj: Directed adjacency list.
        papers: UID to Paper lookup for metadata.
        path: Output file path.  Supported extensions: ``.json``, ``.gv``,
            ``.dot``, ``.md``, ``.markdown``.
        clusters: Optional cluster assignments (used for JSON export only).

    Raises:
        ValueError: If the file extension is not supported.
    """
    suffix = path.suffix.lower()
    if suffix == ".json":
        content = to_json(nodes, adj, papers, clusters)
    elif suffix in {".gv", ".dot"}:
        content = to_dot(nodes, adj, papers)
    elif suffix in {".md", ".markdown"}:
        content = to_mermaid(nodes, adj, papers)
    else:
        raise ValueError(f"Unsupported format {suffix!r} — use .json, .gv, or .md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
