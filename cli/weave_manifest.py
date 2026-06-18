"""Pure logic for the HTML artifact chain: build the machine manifest and
validate the agent-emitted HTML.

This module never spawns an agent and never mutates global state. `build_manifest`
folds the spec workspace into a deterministic dict (the `chain.json` contract);
`validate_chain_html` is the non-determinism guard for the agent's `chain.html`
output. Both are fully unit-testable.

The stage list is imported from `cli.pipeline.STAGES` (single source of truth) so
the manifest never drifts from the pipeline definition.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from cli.pipeline import STAGES

# A markdown link `[text](url)` or a bare numeric ref `[12]` — counted as a
# citation signal. Deterministic, no agent.
_CITATION_RE = re.compile(r"\[[^\]]+\]\([^)]+\)|\[\d+\]")
_HEADING_RE = re.compile(r"^#+\s+(.*)$")


def _count_citations(text: str) -> int:
    return len(_CITATION_RE.findall(text))


def _headings(text: str) -> List[str]:
    out: List[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            heading = m.group(1).strip()
            if heading:
                out.append(heading)
    return out


def _stage_entry(name: str, artifact: str, workspace: Path) -> Dict[str, object]:
    """Build one manifest stage entry. File vs directory artifacts differ."""
    path = workspace / artifact
    if artifact.endswith("/"):
        files = 0
        if path.exists() and path.is_dir():
            files = sum(1 for p in path.iterdir() if p.is_file())
        return {
            "name": name,
            "artifact": artifact,
            "exists": path.exists(),
            "is_dir": True,
            "files": files,
        }
    exists = path.exists() and path.is_file()
    entry: Dict[str, object] = {
        "name": name,
        "artifact": artifact,
        "exists": exists,
    }
    if exists:
        text = path.read_text()
        entry["bytes"] = len(text.encode("utf-8"))
        entry["citations"] = _count_citations(text)
        entry["headings"] = _headings(text)
    return entry


def build_manifest(
    workspace: Path,
    topic: str = "",
    slug: str = "",
) -> Dict[str, object]:
    """Fold a spec workspace into the chain.json manifest dict.

    Deterministic and side-effect free: no timestamp is generated here (callers
    that want one pass it in / stamp the file afterward), mirroring
    `board.Event.ts`. The stage list comes from `pipeline.STAGES`.
    """
    stages: List[Dict[str, object]] = [
        _stage_entry(s["name"], s["artifact"], workspace) for s in STAGES
    ]
    missing = [s["name"] for s in stages if not s["exists"]]
    return {
        "topic": topic,
        "slug": slug or (workspace.name if workspace else ""),
        "workspace": str(workspace),
        "generated_from": "weave",
        "stages": stages,
        "chain_complete": not missing,
        "missing": missing,
    }


def present_file_stages(manifest: Dict[str, object]) -> List[Dict[str, object]]:
    """Stages that exist AND are file artifacts (inlinable into context/HTML)."""
    out: List[Dict[str, object]] = []
    for s in manifest.get("stages", []):
        if s.get("exists") and not s.get("is_dir"):
            out.append(s)
    return out


def validate_chain_html(html: str, expected_stages: List[str]) -> List[str]:
    """Check the agent's chain.html is well-formed and covers each present stage.

    Returns a list of problems (empty == valid). This is a guard, not a parser:
    we assert structural sanity, never exact bytes (agent output is
    non-deterministic).
    """
    problems: List[str] = []
    text = html or ""
    if not text.strip():
        return ["chain.html is empty"]
    lower = text.lower()
    if "<html" not in lower:
        problems.append("missing <html> root element")
    if "</html>" not in lower:
        problems.append("missing closing </html> tag")
    if "<body" not in lower:
        problems.append("missing <body> element")
    for stage in expected_stages:
        if stage.lower() not in lower:
            problems.append(f"no section for stage '{stage}'")
    return problems
