"""Append-only event log that backs the kanban board.

Hermes (and the loop) append one JSONL event per stage/status transition. The
board is a pure projection over these events — it never mutates them, so there
is no shared state to coordinate. Timestamps are passed in by the caller (never
generated here) so the projection stays deterministic and testable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

EVENTS_FILENAME = "events.jsonl"

# Recognized status values (free-form is tolerated, these document the contract).
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"


@dataclass
class Event:
    task: str
    stage: str
    status: str
    agent: Optional[str] = None
    verdict: Optional[str] = None
    ts: Optional[str] = None


def events_path(workspace: Path) -> Path:
    return workspace / EVENTS_FILENAME


def append_event(workspace: Path, event: Event) -> Path:
    """Append one event as a JSONL line, creating the workspace if needed."""
    workspace.mkdir(parents=True, exist_ok=True)
    path = events_path(workspace)
    with path.open("a") as fh:
        fh.write(json.dumps(asdict(event), sort_keys=True) + "\n")
    return path


def read_events(workspace: Path) -> List[Event]:
    """Read all events. Corrupt/non-JSON lines are skipped (read-model is lenient)."""
    path = events_path(workspace)
    if not path.exists():
        return []
    out: List[Event] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict) or "task" not in data:
            continue
        out.append(
            Event(
                task=data.get("task", ""),
                stage=data.get("stage", ""),
                status=data.get("status", ""),
                agent=data.get("agent"),
                verdict=data.get("verdict"),
                ts=data.get("ts"),
            )
        )
    return out


def latest_by_task(evs: List[Event]) -> Dict[str, Event]:
    """Fold events into the latest event per task (last write wins)."""
    latest: Dict[str, Event] = {}
    for e in evs:
        latest[e.task] = e
    return latest
