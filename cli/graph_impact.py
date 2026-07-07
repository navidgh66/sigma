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
from typing import Dict, List, Optional

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
