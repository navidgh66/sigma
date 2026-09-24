"""sigma /loop Stop hook: keep an unattended loop running until its tasks settle.

Opus 5.5 guide: a text-only end of turn is a report, not proof the work is done.
When a sigma loop is running and tasks are still open with no recorded blocker,
this hook blocks the stop and names the open tasks. It nudges at most
`max_nudges` times without progress, then lets the run stop (status "stopped")
so a stuck run ends and can be reviewed.

Stdlib only (the plugin checkout is separate from the CLI). Fails open: any
error means exit 0 with no output, so a broken guard never traps a session.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

OPEN_STATUSES = ("open", "in_progress")
DEFAULT_MAX_NUDGES = 3
_MAX_LISTED = 8


@dataclass
class Decision:
    block: bool
    reason: str = ""
    state: Optional[dict] = None  # updated state to write back; None = no write


def _open_tasks(state: dict) -> List[dict]:
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [t for t in tasks if isinstance(t, dict) and t.get("status") in OPEN_STATUSES]


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _elapsed(state: dict, now: datetime) -> str:
    try:
        started = datetime.fromisoformat(str(state["started_at"]).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return ""
    secs = max(0, int((now - started).total_seconds()))
    budget = state.get("budget_seconds")
    if isinstance(budget, int) and budget > 0:
        return f" (elapsed {secs}s / {budget}s)"
    return f" (elapsed {secs}s)"


def _nudge(open_list: List[dict], elapsed: str) -> str:
    names = [f"{t.get('id', '?')} ({t.get('title', '')})" for t in open_list[:_MAX_LISTED]]
    more = len(open_list) - _MAX_LISTED
    listed = ", ".join(names) + (f", +{more} more" if more > 0 else "")
    return (
        f"Your loop still has open tasks: {listed}. Continue with them. If one is "
        "blocked, set `blocker` in loop-state.json and say what blocks it." + elapsed
    )


def decide(state: Optional[dict], now: datetime) -> Decision:
    """Pure decision: block the stop (with a nudge) or allow it."""
    if not isinstance(state, dict) or state.get("status") != "running":
        return Decision(block=False)
    if state.get("blocker"):
        return Decision(block=False)
    open_list = _open_tasks(state)
    if not open_list:
        return Decision(block=False)
    new = copy.deepcopy(state)
    nudges = _int(new.get("nudges"), 0)
    prev_open = new.get("nudge_open_count")
    if isinstance(prev_open, int) and len(open_list) < prev_open:
        nudges = 0  # progress since the last nudge
    if nudges >= _int(new.get("max_nudges"), DEFAULT_MAX_NUDGES):
        new["status"] = "stopped"
        return Decision(block=False, state=new)
    new["nudges"] = nudges + 1
    new["nudge_open_count"] = len(open_list)
    return Decision(block=True, reason=_nudge(open_list, _elapsed(state, now)), state=new)


def _load(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def find_running_state(cwd: Path) -> Optional[Path]:
    """Newest running sigma/specs/*/loop-state.json at cwd or its nearest ancestor."""
    for base in [cwd, *cwd.parents]:
        specs = base / "sigma" / "specs"
        if not specs.is_dir():
            continue
        running = []
        for p in specs.glob("*/loop-state.json"):
            state = _load(p)
            if state and state.get("status") == "running":
                running.append(p)
        if running:
            return max(running, key=lambda p: p.stat().st_mtime)
        return None
    return None


def main(stdin_text: str, now: Optional[datetime] = None) -> Tuple[int, str]:
    try:
        try:
            hook_input = json.loads(stdin_text) if stdin_text.strip() else {}
        except ValueError:
            hook_input = {}
        if not isinstance(hook_input, dict):
            hook_input = {}
        cwd = Path(hook_input.get("cwd") or os.getcwd())
        path = find_running_state(cwd)
        if path is None:
            return 0, ""
        state = _load(path)
        decision = decide(state, now or datetime.now(timezone.utc))
        if decision.state is not None:
            try:
                path.write_text(json.dumps(decision.state, indent=2) + "\n")
            except OSError:
                pass
        if decision.block:
            return 0, json.dumps({"decision": "block", "reason": decision.reason})
        return 0, ""
    except Exception:  # noqa: BLE001 - a Stop hook must never break a session
        return 0, ""


if __name__ == "__main__":
    code, out = main(sys.stdin.read())
    if out:
        print(out)
    sys.exit(code)
