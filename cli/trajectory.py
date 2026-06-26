"""Agent trajectory capture — observability over what agents actually did.

The Google "New SDLC" paper makes the point that without observability there is
no way to tell whether an agent is doing well or quietly drifting. Sigma's loop
and hermes already record *outcomes* (events.jsonl) and *cost* (costs.jsonl).
This module records the *trajectory*: one append-only step per agent run (role,
model, ok, duration), so a human can audit how a result was reached, not just
what it was.

Same discipline as `events.py` / `cost.py`:
  - pure: no clock, no subprocess — the caller passes `ts`;
  - append-only JSONL (`trajectory.jsonl`) in the spec workspace;
  - the read model is lenient (corrupt lines skipped, missing file → empty);
  - `summarize` is a pure projection (deterministic, testable).

`AgentRunner` emits a step dict via an injected `trajectory_sink`; `make_sink`
builds a workspace-bound sink that stamps each step with a run timestamp. The
sink is best-effort — a write failure is swallowed so observability never breaks
a run (the inverse of a hard gate).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

TRAJECTORY_FILENAME = "trajectory.jsonl"


@dataclass
class TrajectoryStep:
    role: str
    model: Optional[str] = None
    ok: bool = True
    returncode: int = 0
    error: Optional[str] = None
    output_chars: int = 0
    duration_s: float = 0.0
    ts: Optional[str] = None


def trajectory_path(workspace: Path) -> Path:
    return workspace / TRAJECTORY_FILENAME


def build_step(raw: dict, ts: Optional[str] = None) -> TrajectoryStep:
    """Build a TrajectoryStep from a runner's step dict (caller passes `ts`)."""
    raw = raw or {}
    return TrajectoryStep(
        role=str(raw.get("role", "agent")),
        model=raw.get("model"),
        ok=bool(raw.get("ok", True)),
        returncode=int(raw.get("returncode", 0) or 0),
        error=raw.get("error"),
        output_chars=int(raw.get("output_chars", 0) or 0),
        duration_s=float(raw.get("duration_s", 0.0) or 0.0),
        ts=ts if ts is not None else raw.get("ts"),
    )


def append_step(workspace: Path, step: TrajectoryStep) -> Path:
    """Append one step as a JSONL line, creating the workspace if needed."""
    workspace.mkdir(parents=True, exist_ok=True)
    path = trajectory_path(workspace)
    with path.open("a") as fh:
        fh.write(json.dumps(asdict(step), sort_keys=True) + "\n")
    return path


def read_steps(workspace: Path) -> List[TrajectoryStep]:
    """Read all steps. Corrupt/non-JSON lines are skipped (lenient read-model)."""
    path = trajectory_path(workspace)
    if not path.exists():
        return []
    out: List[TrajectoryStep] = []
    try:
        text = path.read_text()
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict) or "role" not in data:
            continue
        out.append(build_step(data, ts=data.get("ts")))
    return out


def make_sink(workspace: Path, ts: Optional[str] = None) -> Callable[[dict], None]:
    """Return a sink that appends each runner step dict to the workspace trajectory.

    Best-effort: a write failure (read-only fs, blocked path) is swallowed so the
    agent run is never broken by observability. Each step is stamped with `ts`.
    """

    def sink(raw: dict) -> None:
        try:
            append_step(workspace, build_step(raw, ts=ts))
        except OSError:
            pass

    return sink


# --------------------------------------------------------------------------- #
# Projection
# --------------------------------------------------------------------------- #
@dataclass
class TrajectorySummary:
    total: int = 0
    failures: int = 0
    by_role: Dict[str, int] = field(default_factory=dict)
    by_model: Dict[str, int] = field(default_factory=dict)
    total_duration_s: float = 0.0

    def render(self) -> str:
        if self.total == 0:
            return "# trajectory\n\nNo agent steps recorded yet."
        lines = [
            "# trajectory",
            "",
            f"**{self.total} step(s)**, {self.failures} failed, "
            f"{self.total_duration_s:.1f}s total agent time.",
            "",
            "## By role",
            "",
        ]
        for role in sorted(self.by_role, key=lambda r: self.by_role[r], reverse=True):
            lines.append(f"- **{role}**: {self.by_role[role]} step(s)")
        if self.by_model:
            lines += ["", "## By model", ""]
            for model in sorted(self.by_model, key=lambda m: self.by_model[m], reverse=True):
                lines.append(f"- **{model or '(default)'}**: {self.by_model[model]} step(s)")
        return "\n".join(lines)


def summarize(steps: List[TrajectoryStep]) -> TrajectorySummary:
    """Pure projection: fold steps into counts + per-role/model tallies + duration."""
    summary = TrajectorySummary()
    for s in steps:
        summary.total += 1
        if not s.ok:
            summary.failures += 1
        summary.by_role[s.role] = summary.by_role.get(s.role, 0) + 1
        key = s.model or ""
        summary.by_model[key] = summary.by_model.get(key, 0) + 1
        summary.total_duration_s += s.duration_s
    summary.total_duration_s = round(summary.total_duration_s, 3)
    return summary
