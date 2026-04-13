"""Tests for mosaic/network.py — graph analysis, clustering, and export."""

import json

import pytest

from mosaic.models import Paper
from mosaic.network import (
    build_adj,
    compute_degree,
    connected_components,
    count_edges,
    export_graph,
    louvain_clusters,
    subgraph_from_seeds,
    to_dot,
    to_json,
    to_mermaid,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _paper(uid_doi: str, title: str, year: int = 2020) -> Paper:
    return Paper(title=title, doi=uid_doi, year=year, source="test")


def _make_papers(uids: list[str]) -> dict[str, Paper]:
    return {uid: _paper(uid, f"Paper about {uid}", 2020 + i) for i, uid in enumerate(uids)}


# ── build_adj ─────────────────────────────────────────────────────────────────


class TestBuildAdj:
    def test_directed_edges_stored(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        assert "doi:b" in adj["doi:a"]
        assert "doi:c" in adj["doi:b"]

    def test_target_only_nodes_have_empty_list(self):
        adj = build_adj([("doi:a", "doi:b")])
        assert "doi:b" in adj
        assert adj["doi:b"] == []

    def test_empty_edges(self):
        adj = build_adj([])
        assert adj == {}

    def test_duplicate_edges_kept(self):
        # build_adj does not deduplicate; that is the DB's responsibility
        adj = build_adj([("doi:a", "doi:b"), ("doi:a", "doi:b")])
        assert adj["doi:a"].count("doi:b") == 2


# ── subgraph_from_seeds ───────────────────────────────────────────────────────


class TestSubgraphFromSeeds:
    def test_depth_zero_returns_seeds_only(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        nodes = subgraph_from_seeds(adj, ["doi:a"], depth=0)
        assert nodes == {"doi:a"}

    def test_depth_one_follows_one_hop(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        nodes = subgraph_from_seeds(adj, ["doi:a"], depth=1)
        assert "doi:b" in nodes
        assert "doi:c" not in nodes

    def test_depth_two_follows_two_hops(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        nodes = subgraph_from_seeds(adj, ["doi:a"], depth=2)
        assert {"doi:a", "doi:b", "doi:c"} == nodes

    def test_undirected_traversal(self):
        # Edge goes b -> a; seeding from a should still reach b
        adj = build_adj([("doi:b", "doi:a")])
        nodes = subgraph_from_seeds(adj, ["doi:a"], depth=1)
        assert "doi:b" in nodes

    def test_unknown_seed_ignored(self):
        adj = build_adj([("doi:a", "doi:b")])
        nodes = subgraph_from_seeds(adj, ["doi:unknown"], depth=2)
        assert nodes == set()

    def test_multiple_seeds(self):
        adj = build_adj([("doi:a", "doi:c"), ("doi:b", "doi:d")])
        nodes = subgraph_from_seeds(adj, ["doi:a", "doi:b"], depth=1)
        assert {"doi:a", "doi:b", "doi:c", "doi:d"} == nodes


# ── compute_degree ────────────────────────────────────────────────────────────


class TestComputeDegree:
    def test_degree_counts_undirected(self):
        # a -> b -> c; degree of b in full graph = 2 (neighbour of a and c)
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        nodes = {"doi:a", "doi:b", "doi:c"}
        deg = compute_degree(adj, nodes)
        assert deg["doi:b"] == 2

    def test_isolated_node_has_degree_zero(self):
        adj = build_adj([("doi:a", "doi:b")])
        adj["doi:isolated"] = []
        deg = compute_degree(adj, {"doi:isolated"})
        assert deg["doi:isolated"] == 0

    def test_edges_outside_nodes_not_counted(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        # Only include a and b; edge b->c is outside the subgraph
        deg = compute_degree(adj, {"doi:a", "doi:b"})
        assert deg["doi:b"] == 1


# ── count_edges ───────────────────────────────────────────────────────────────


class TestCountEdges:
    def test_simple_chain(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        assert count_edges({"doi:a", "doi:b", "doi:c"}, adj) == 2

    def test_edges_outside_nodes_excluded(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        # Only doi:a and doi:b in subgraph
        assert count_edges({"doi:a", "doi:b"}, adj) == 1

    def test_bidirectional_counted_once(self):
        # a->b and b->a represent one undirected edge
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:a")])
        assert count_edges({"doi:a", "doi:b"}, adj) == 1


# ── connected_components ──────────────────────────────────────────────────────


class TestConnectedComponents:
    def test_single_component(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        comps = connected_components({"doi:a", "doi:b", "doi:c"}, adj)
        assert len(comps) == 1
        assert comps[0] == {"doi:a", "doi:b", "doi:c"}

    def test_two_components(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:c", "doi:d")])
        comps = connected_components({"doi:a", "doi:b", "doi:c", "doi:d"}, adj)
        assert len(comps) == 2

    def test_sorted_largest_first(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c"), ("doi:x", "doi:y")])
        comps = connected_components({"doi:a", "doi:b", "doi:c", "doi:x", "doi:y"}, adj)
        assert len(comps[0]) >= len(comps[1])

    def test_isolated_nodes(self):
        adj = {"doi:a": [], "doi:b": []}
        comps = connected_components({"doi:a", "doi:b"}, adj)
        assert len(comps) == 2

    def test_empty_nodes(self):
        adj = build_adj([("doi:a", "doi:b")])
        comps = connected_components(set(), adj)
        assert comps == []


# ── louvain_clusters ──────────────────────────────────────────────────────────


class TestLouvainClusters:
    def test_returns_list_of_sets(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        nodes = {"doi:a", "doi:b", "doi:c"}
        result = louvain_clusters(nodes, adj)
        assert isinstance(result, list)
        assert all(isinstance(c, set) for c in result)

    def test_all_nodes_covered(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:c", "doi:d")])
        nodes = {"doi:a", "doi:b", "doi:c", "doi:d"}
        result = louvain_clusters(nodes, adj)
        covered = set().union(*result)
        assert covered == nodes

    def test_no_overlap_between_clusters(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:c", "doi:d")])
        nodes = {"doi:a", "doi:b", "doi:c", "doi:d"}
        result = louvain_clusters(nodes, adj)
        all_uids = [uid for comp in result for uid in comp]
        assert len(all_uids) == len(set(all_uids))


# ── to_json ───────────────────────────────────────────────────────────────────


class TestToJson:
    def test_valid_json(self):
        adj = build_adj([("doi:a", "doi:b")])
        nodes = {"doi:a", "doi:b"}
        papers = _make_papers(["doi:a", "doi:b"])
        out = to_json(nodes, adj, papers)
        data = json.loads(out)
        assert "nodes" in data
        assert "links" in data

    def test_node_count(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        nodes = {"doi:a", "doi:b", "doi:c"}
        papers = _make_papers(list(nodes))
        data = json.loads(to_json(nodes, adj, papers))
        assert len(data["nodes"]) == 3

    def test_edge_count(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        nodes = {"doi:a", "doi:b", "doi:c"}
        papers = _make_papers(list(nodes))
        data = json.loads(to_json(nodes, adj, papers))
        assert len(data["links"]) == 2

    def test_cluster_field_populated(self):
        adj = build_adj([("doi:a", "doi:b")])
        nodes = {"doi:a", "doi:b"}
        papers = _make_papers(list(nodes))
        clusters = [{"doi:a"}, {"doi:b"}]
        data = json.loads(to_json(nodes, adj, papers, clusters))
        cluster_vals = {n["id"]: n["cluster"] for n in data["nodes"]}
        assert cluster_vals["doi:a"] != cluster_vals["doi:b"]

    def test_unknown_uid_uses_uid_as_title(self):
        adj = build_adj([("doi:a", "doi:b")])
        nodes = {"doi:a", "doi:b"}
        data = json.loads(to_json(nodes, adj, {}))
        titles = {n["id"]: n["title"] for n in data["nodes"]}
        assert titles["doi:a"] == "doi:a"


# ── to_dot ────────────────────────────────────────────────────────────────────


class TestToDot:
    def test_starts_with_graph(self):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = to_dot({"doi:a", "doi:b"}, adj, papers)
        assert out.startswith("graph G {")

    def test_contains_edge(self):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = to_dot({"doi:a", "doi:b"}, adj, papers)
        assert " -- " in out

    def test_no_edges_outside_nodes(self):
        adj = build_adj([("doi:a", "doi:b"), ("doi:b", "doi:c")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = to_dot({"doi:a", "doi:b"}, adj, papers)
        assert "doi:c" not in out


# ── to_mermaid ────────────────────────────────────────────────────────────────


class TestToMermaid:
    def test_fenced_code_block(self):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = to_mermaid({"doi:a", "doi:b"}, adj, papers)
        assert out.startswith("```mermaid")
        assert out.endswith("```")

    def test_contains_edge_arrow(self):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = to_mermaid({"doi:a", "doi:b"}, adj, papers)
        assert " --- " in out


# ── export_graph ──────────────────────────────────────────────────────────────


class TestExportGraph:
    def test_json_written(self, tmp_path):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = tmp_path / "graph.json"
        export_graph({"doi:a", "doi:b"}, adj, papers, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert "nodes" in data

    def test_dot_written(self, tmp_path):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = tmp_path / "graph.gv"
        export_graph({"doi:a", "doi:b"}, adj, papers, out)
        assert out.exists()
        assert out.read_text().startswith("graph G {")

    def test_md_written(self, tmp_path):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = tmp_path / "graph.md"
        export_graph({"doi:a", "doi:b"}, adj, papers, out)
        assert out.exists()
        assert "mermaid" in out.read_text()

    def test_unsupported_format_raises(self, tmp_path):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        with pytest.raises(ValueError, match="Unsupported format"):
            export_graph({"doi:a", "doi:b"}, adj, papers, tmp_path / "graph.xyz")

    def test_parent_dir_created(self, tmp_path):
        adj = build_adj([("doi:a", "doi:b")])
        papers = _make_papers(["doi:a", "doi:b"])
        out = tmp_path / "subdir" / "graph.json"
        export_graph({"doi:a", "doi:b"}, adj, papers, out)
        assert out.exists()


# ── db integration ────────────────────────────────────────────────────────────


class TestDbIntegration:
    def test_get_all_citation_edges(self, tmp_cache):
        p1 = _paper("10.1/a", "Paper A")
        p2 = _paper("10.1/b", "Paper B")
        tmp_cache.save(p1)
        tmp_cache.save(p2)
        tmp_cache.upsert_citation_edges([(p1.uid, p2.uid, "openalex")])
        edges = tmp_cache.get_all_citation_edges()
        assert (p1.uid, p2.uid) in edges

    def test_empty_edges_returns_empty_list(self, tmp_cache):
        assert tmp_cache.get_all_citation_edges() == []

    def test_multiple_edges(self, tmp_cache):
        papers = [_paper(f"10.1/{c}", f"Paper {c}") for c in "abc"]
        for p in papers:
            tmp_cache.save(p)
        uids = [p.uid for p in papers]
        edges_in = [(uids[0], uids[1], "openalex"), (uids[1], uids[2], "crossref")]
        tmp_cache.upsert_citation_edges(edges_in)
        edges_out = tmp_cache.get_all_citation_edges()
        assert len(edges_out) == 2
