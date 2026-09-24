"""Tests for the plugin Stop hook (hooks/loop_guard.py)."""

import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "hooks" / "loop_guard.py"
_spec = importlib.util.spec_from_file_location("loop_guard", _PATH)
lg = importlib.util.module_from_spec(_spec)
sys.modules["loop_guard"] = lg  # dataclasses resolve the module via sys.modules
_spec.loader.exec_module(lg)

NOW = datetime(2026, 9, 24, 10, 5, 40, tzinfo=timezone.utc)


def _state(**over):
    s = {
        "version": 1, "status": "running", "topic": "t",
        "started_at": "2026-09-24T10:00:00Z", "budget_seconds": None,
        "max_nudges": 3, "nudges": 0, "nudge_open_count": None, "blocker": None,
        "tasks": [
            {"id": "T1", "title": "done one", "status": "passed"},
            {"id": "T3", "title": "add tokenizer cache", "status": "open"},
            {"id": "T5", "title": "eval split", "status": "in_progress"},
        ],
    }
    s.update(over)
    return s


def test_allow_when_no_state():
    assert lg.decide(None, NOW).block is False


def test_allow_when_not_running():
    assert lg.decide(_state(status="done"), NOW).block is False


def test_allow_when_blocker_recorded():
    assert lg.decide(_state(blocker="needs API key"), NOW).block is False


def test_allow_when_all_tasks_settled():
    tasks = [{"id": "T1", "title": "a", "status": "passed"}, {"id": "T2", "title": "b", "status": "failed"}]
    assert lg.decide(_state(tasks=tasks), NOW).block is False


def test_block_names_open_tasks_and_counts_nudge():
    d = lg.decide(_state(), NOW)
    assert d.block is True
    assert "T3 (add tokenizer cache)" in d.reason and "T5 (eval split)" in d.reason
    assert "blocker" in d.reason
    assert d.state["nudges"] == 1 and d.state["nudge_open_count"] == 2


def test_cap_reached_allows_and_marks_stopped():
    d = lg.decide(_state(nudges=3, nudge_open_count=2), NOW)
    assert d.block is False
    assert d.state["status"] == "stopped"


def test_progress_resets_nudges():
    d = lg.decide(_state(nudges=3, nudge_open_count=5), NOW)  # was 5 open, now 2
    assert d.block is True
    assert d.state["nudges"] == 1


def test_elapsed_without_and_with_budget():
    assert "(elapsed 340s)" in lg.decide(_state(), NOW).reason
    assert "(elapsed 340s / 1200s)" in lg.decide(_state(budget_seconds=1200), NOW).reason


def test_garbage_fields_do_not_crash():
    assert lg.decide(_state(tasks="nope"), NOW).block is False
    d = lg.decide(_state(started_at="garbage", max_nudges="x"), NOW)
    assert d.block is True and "elapsed" not in d.reason


def _write(ws: Path, state) -> Path:
    ws.mkdir(parents=True, exist_ok=True)
    p = ws / "loop-state.json"
    p.write_text(json.dumps(state) if isinstance(state, dict) else state)
    return p


def test_find_running_state_walks_up_and_picks_newest(tmp_path):
    old = _write(tmp_path / "sigma" / "specs" / "a", _state())
    new = _write(tmp_path / "sigma" / "specs" / "b", _state())
    _write(tmp_path / "sigma" / "specs" / "c", _state(status="done"))
    os.utime(old, (time.time() - 100, time.time() - 100))
    sub = tmp_path / "src" / "pkg"
    sub.mkdir(parents=True)
    assert lg.find_running_state(sub) == new


def test_main_blocks_and_writes_back(tmp_path):
    p = _write(tmp_path / "sigma" / "specs" / "a", _state())
    code, out = lg.main(json.dumps({"cwd": str(tmp_path)}), now=NOW)
    assert code == 0
    assert json.loads(out)["decision"] == "block"
    assert json.loads(p.read_text())["nudges"] == 1


def test_main_fail_open_on_garbage(tmp_path):
    _write(tmp_path / "sigma" / "specs" / "a", "{not json")
    assert lg.main(json.dumps({"cwd": str(tmp_path)}), now=NOW) == (0, "")
    assert lg.main("not json at all", now=NOW) == (0, "")


def test_hooks_json_registers_stop_guard():
    cfg = json.loads((_PATH.parent / "hooks.json").read_text())
    cmd = cfg["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "loop_guard.py" in cmd and "${CLAUDE_PLUGIN_ROOT}" in cmd
