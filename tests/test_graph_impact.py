"""Tests for cli/graph_impact — fail-safe graph.json reader + diff-impact."""

import json
from pathlib import Path

from cli.graph_impact import load_graph


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
