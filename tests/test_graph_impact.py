"""Tests for cli/graph_impact — fail-safe graph.json reader + diff-impact."""

import json
from pathlib import Path

from cli.graph_impact import FileImpact, impact_for, load_graph


def _write_graph(root: Path, obj) -> None:
    out = root / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps(obj))


def test_load_graph_happy(tmp_path):
    _write_graph(tmp_path, {"nodes": [], "edges": []})
    assert load_graph(tmp_path) == {"nodes": [], "edges": []}


def test_load_graph_missing_returns_none(tmp_path):
    assert load_graph(tmp_path) is None


def test_load_graph_bad_json_returns_none(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True)
    (out / "graph.json").write_text("{not json")
    assert load_graph(tmp_path) is None


def test_load_graph_oversize_returns_none(tmp_path):
    _write_graph(tmp_path, {"nodes": [{"id": "x" * 100}]})
    assert load_graph(tmp_path, max_bytes=10) is None


def test_impact_canonical_schema():
    graph = {
        "nodes": [
            {"id": "n1", "name": "Foo", "file": "cli/foo.py"},
            {"id": "n2", "name": "Bar", "file": "cli/bar.py"},
        ],
        "edges": [{"source": "n2", "target": "n1"}],  # Bar depends on Foo
    }
    out = impact_for(graph, ["cli/foo.py"])
    assert out == [FileImpact(file="cli/foo.py", nodes=["Foo"], dependents=["Bar"])]


def test_impact_alt_schema_links_from_to_path():
    graph = {
        "nodes": [
            {"id": "a", "label": "A", "path": "/abs/repo/cli/a.py"},
            {"id": "b", "label": "B", "path": "/abs/repo/cli/b.py"},
        ],
        "links": [{"from": "b", "to": "a"}],
    }
    out = impact_for(graph, ["cli/a.py"])  # matches by suffix (abs vs relative)
    assert out[0].nodes == ["A"]
    assert out[0].dependents == ["B"]


def test_impact_edge_endpoints_by_name():
    graph = {
        "nodes": [{"name": "Foo", "file": "cli/foo.py"},
                  {"name": "Bar", "file": "cli/bar.py"}],
        "edges": [{"source": "Bar", "target": "Foo"}],  # endpoints are names, not ids
    }
    out = impact_for(graph, ["cli/foo.py"])
    assert out[0].dependents == ["Bar"]


def test_impact_no_match_returns_empty_lists():
    graph = {"nodes": [{"name": "Foo", "file": "cli/foo.py"}], "edges": []}
    out = impact_for(graph, ["cli/unrelated.py"])
    assert out == [FileImpact(file="cli/unrelated.py", nodes=[], dependents=[])]


def test_impact_malformed_nodes_skipped_no_crash():
    graph = {"nodes": ["not a dict", {"file": "cli/foo.py"}, {"name": "Ok", "file": "cli/foo.py"}],
             "edges": ["bad", {"source": "x"}]}
    out = impact_for(graph, ["cli/foo.py"])
    assert out[0].nodes == ["Ok"]  # nameless + non-dict nodes skipped, no raise


def test_impact_caps_and_dedup():
    nodes = [{"name": f"N{i}", "file": "cli/foo.py"} for i in range(30)]
    nodes.append({"name": "N0", "file": "cli/foo.py"})  # dup
    out = impact_for({"nodes": nodes, "edges": []}, ["cli/foo.py"])
    assert len(out[0].nodes) == 20  # _PER_FILE_CAP
    assert out[0].nodes == sorted(set(n["name"] for n in nodes))[:20]
