"""Graph-aware diff impact for `sigma review` (read side of graphify's graph.json).

Reads graphify's `graphify-out/graph.json` with stdlib json — sigma NEVER imports
graphify (it needs 3.10+; sigma stays 3.9). Cross-references a review's changed
files against the graph: which nodes each file defines, and which other nodes depend
on them (reverse edges). Purely informational — the review gate and axis prompts are
untouched. Fail-safe: no graph, or an unrecognized schema, yields empty impact (or
None from load_graph), never a crash.

graphify's graph.json schema is not a stable contract, so parsing is deliberately
tolerant: it tries several common key names and skips anything it can't read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

_GRAPH_REL = ("graphify-out", "graph.json")
# Guard against a pathological graph.json blowing memory / the report.
_DEFAULT_MAX_BYTES = 20_000_000
# Per-file cap on nodes/dependents surfaced (report stays readable).
_PER_FILE_CAP = 20


def load_graph(root: Path, max_bytes: int = _DEFAULT_MAX_BYTES) -> Optional[dict]:
    """Parse graphify's graph.json under `root`. None on any failure (fail-safe)."""
    path = root
    for part in _GRAPH_REL:
        path = path / part
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            return None
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


_NODE_PATH_KEYS = ("file", "path", "source", "source_file")
_NODE_NAME_KEYS = ("name", "label", "id")
_EDGE_SRC_KEYS = ("source", "from", "src")
_EDGE_DST_KEYS = ("target", "to", "dst")


@dataclass(frozen=True)
class FileImpact:
    file: str
    nodes: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)


def _first(d: dict, keys) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _matches(node_path: str, changed: str) -> bool:
    """A node belongs to `changed` when its path equals or ends with it (abs vs rel)."""
    np = node_path.replace("\\", "/")
    ch = changed.replace("\\", "/")
    return np == ch or np.endswith("/" + ch) or np.endswith(ch)


def impact_for(graph: dict, changed_files: Sequence[str]) -> List[FileImpact]:
    """Per-file (nodes defined, dependents = nodes with an edge INTO those nodes).

    Schema-tolerant + fail-safe: unreadable nodes/edges are skipped, never raised.
    Deterministic: changed_files order preserved; nodes/dependents sorted, deduped,
    capped at _PER_FILE_CAP.
    """
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    edges = graph.get("edges") if isinstance(graph, dict) else None
    if edges is None and isinstance(graph, dict):
        edges = graph.get("links")
    nodes = nodes if isinstance(nodes, list) else []
    edges = edges if isinstance(edges, list) else []

    # Build: node-name-or-id → path; and id/name → display name (for edge resolution).
    name_by_key: Dict[str, str] = {}
    path_by_name: Dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        name = _first(n, _NODE_NAME_KEYS)
        if not name:
            continue
        path = _first(n, _NODE_PATH_KEYS)
        # Register every possible edge-endpoint key (id, name, label) → display name.
        for k in _NODE_NAME_KEYS:
            v = n.get(k)
            if isinstance(v, str) and v:
                name_by_key[v] = name
        if path:
            path_by_name.setdefault(name, path)

    results: List[FileImpact] = []
    for changed in changed_files:
        touched = sorted({
            name for name, path in path_by_name.items() if _matches(path, changed)
        })
        touched_set = set(touched)
        dependents = set()
        for e in edges:
            if not isinstance(e, dict):
                continue
            src = _first(e, _EDGE_SRC_KEYS)
            dst = _first(e, _EDGE_DST_KEYS)
            if not src or not dst:
                continue
            dst_name = name_by_key.get(dst, dst)
            if dst_name in touched_set:
                src_name = name_by_key.get(src, src)
                if src_name not in touched_set:  # a dependent, not a self-edge
                    dependents.add(src_name)
        results.append(FileImpact(
            file=changed,
            nodes=touched[:_PER_FILE_CAP],
            dependents=sorted(dependents)[:_PER_FILE_CAP],
        ))
    return results


def render_impact_section(impacts: List[FileImpact]) -> str:
    """Render the informational Impact markdown block (never affects the gate)."""
    header = "## Impact (knowledge graph)"
    preamble = (
        "_Derived from graphify's `graph.json`; informational only — does not affect "
        "the review verdict._"
    )
    has_any = any(fi.nodes or fi.dependents for fi in impacts)
    if not has_any:
        return f"{header}\n\n{preamble}\n\n_No graph nodes matched the changed files._\n"

    lines = [header, "", preamble, ""]
    for fi in impacts:
        if not (fi.nodes or fi.dependents):
            continue
        nodes = ", ".join(fi.nodes) if fi.nodes else "—"
        deps = ", ".join(fi.dependents) if fi.dependents else "none"
        lines.append(f"- **{fi.file}** → nodes: {nodes} · dependents: {deps}")
    lines.append("")
    return "\n".join(lines)
