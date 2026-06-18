"""Tests for cli.hermes — the conductor (router + autonomy + events + log)."""

from __future__ import annotations

from pathlib import Path

from cli import events, hermes
from cli.runner import AgentResult


class FakeRunner:
    def __init__(self, reply="", ok=True):
        self._reply = reply
        self._ok = ok

    def run(self, prompt, cwd=None):
        return AgentResult(ok=self._ok, output=self._reply)


def _ws(tmp_path: Path, artifacts=()) -> Path:
    ws = tmp_path / "spec"
    ws.mkdir()
    for a in artifacts:
        (ws / a).write_text("x")
    return ws


def _recording_executor(calls, ok=True, output="done", verdict=None):
    """Build an execute_stage stand-in that records the stages it ran."""

    def _exec(stage_name, workspace, agent=None):
        calls.append(stage_name)
        out = output
        if stage_name == "verify" and verdict:
            out = f"VERDICT: {verdict}"
        return AgentResult(ok=ok, output=out)

    return _exec


# --------------------------- single step --------------------------- #
def test_single_step_runs_one_stage(tmp_path):
    ws = _ws(tmp_path, ["research.md"])
    calls = []
    result = hermes.run_hermes(
        "continue",
        ws,
        execute=_recording_executor(calls),
        make_runner=lambda: FakeRunner(),
    )
    assert calls == ["propose"]  # state next after research.md
    assert result.stages_run == ["propose"]
    assert not result.auto


def test_single_step_emits_events(tmp_path):
    ws = _ws(tmp_path, ["research.md"])
    hermes.run_hermes(
        "continue", ws, execute=_recording_executor([]), make_runner=lambda: FakeRunner(),
        now="2026-06-17T00:00:00",
    )
    evs = events.read_events(ws)
    assert any(e.stage == "propose" and e.status == "done" for e in evs)
    assert any(e.ts == "2026-06-17T00:00:00" for e in evs)


def test_single_step_writes_log(tmp_path):
    ws = _ws(tmp_path, ["research.md"])
    hermes.run_hermes("continue", ws, execute=_recording_executor([]), make_runner=lambda: FakeRunner())
    log = ws / "hermes-log.md"
    assert log.exists()
    assert "propose" in log.read_text()


# --------------------------- auto mode --------------------------- #
def test_auto_runs_chain_until_spec_gate(tmp_path):
    """Auto from empty workspace should stop at the spec approval gate."""
    ws = _ws(tmp_path, [])
    calls = []

    # Executor that also creates the artifact so scan_state advances.
    def _exec(stage_name, workspace, agent=None):
        calls.append(stage_name)
        from cli.pipeline import load_stage

        st = load_stage(stage_name)
        if st and not st.artifact.endswith("/"):
            (workspace / st.artifact).write_text("x")
        return AgentResult(ok=True, output="done")

    result = hermes.run_hermes(
        "build it", ws, auto=True, execute=_exec, make_runner=lambda: FakeRunner(),
    )
    assert calls == ["research", "propose", "blueprint", "spec"]
    assert result.gate == "spec-approval"


def test_auto_stops_on_verify_fail(tmp_path):
    ws = _ws(
        tmp_path,
        ["research.md", "proposals.md", "architecture.md", "spec.md", "tasks.md"],
    )
    calls = []

    def _exec(stage_name, workspace, agent=None):
        calls.append(stage_name)
        from cli.pipeline import load_stage

        st = load_stage(stage_name)
        if st and st.artifact.endswith("/"):
            (workspace / st.artifact.rstrip("/")).mkdir(exist_ok=True)
        out = "VERDICT: FAIL" if stage_name == "verify" else "done"
        return AgentResult(ok=True, output=out)

    result = hermes.run_hermes(
        "go", ws, auto=True, execute=_exec, make_runner=lambda: FakeRunner(),
    )
    assert "verify" in calls
    assert result.gate == "verify-failed"


def test_auto_respects_budget_cap(tmp_path):
    ws = _ws(tmp_path, [])
    calls = []

    def _exec(stage_name, workspace, agent=None):
        calls.append(stage_name)
        from cli.pipeline import load_stage

        st = load_stage(stage_name)
        if st and not st.artifact.endswith("/"):
            (workspace / st.artifact).write_text("x")
        return AgentResult(ok=True, output="done")

    result = hermes.run_hermes(
        "go", ws, auto=True, max_hops=2, execute=_exec, make_runner=lambda: FakeRunner(),
    )
    assert len(calls) == 2
    assert result.gate == "budget-cap"


# --------------------------- failure --------------------------- #
def test_stage_failure_stops_and_reports(tmp_path):
    ws = _ws(tmp_path, ["research.md"])
    result = hermes.run_hermes(
        "continue",
        ws,
        execute=_recording_executor([], ok=False, output=""),
        make_runner=lambda: FakeRunner(),
    )
    assert not result.ok
    assert result.gate == "stage-failed"


# --------------------------- gate --------------------------- #
def _gate(tmp_path, wake):
    p = tmp_path / "g.sh"
    p.write_text(f'#!/bin/sh\necho \'{{"wakeAgent": {"true" if wake else "false"}}}\'\n')
    p.chmod(0o755)
    return str(p)


def test_hermes_gate_skips_before_hop(tmp_path):
    ws = _ws(tmp_path, ["research.md"])
    calls = []
    result = hermes.run_hermes(
        "continue", ws,
        execute=_recording_executor(calls),
        make_runner=lambda: FakeRunner(),
        gate=_gate(tmp_path, wake=False),
    )
    assert calls == []              # gate skipped the hop — no stage ran
    assert result.gate == "wake-gate"


def test_hermes_gate_wakes(tmp_path):
    ws = _ws(tmp_path, ["research.md"])
    calls = []
    hermes.run_hermes(
        "continue", ws,
        execute=_recording_executor(calls),
        make_runner=lambda: FakeRunner(),
        gate=_gate(tmp_path, wake=True),
    )
    assert calls == ["propose"]     # gate woke → ran the hop
