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
def _chain_exec(calls, *, grill="READY"):
    """Executor that writes each artifact (so scan_state advances) and emits a
    READY grill verdict by default so the chain flows past the grill gates."""

    def _exec(stage_name, workspace, agent=None):
        calls.append(stage_name)
        from cli.pipeline import load_stage

        st = load_stage(stage_name)
        if st and not st.artifact.endswith("/"):
            p = workspace / st.artifact
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        out = f"VERDICT: {grill}" if stage_name.startswith("grill-") else "done"
        return AgentResult(ok=True, output=out)

    return _exec


def test_auto_runs_chain_until_spec_gate(tmp_path):
    """Auto from empty workspace should grill the blueprint, then stop at spec gate."""
    ws = _ws(tmp_path, [])
    calls = []
    result = hermes.run_hermes(
        "build it", ws, auto=True, execute=_chain_exec(calls),
        make_runner=lambda: FakeRunner(),
    )
    # grill-blueprint runs (READY) before spec; spec is the human approval gate.
    assert calls == ["research", "propose", "blueprint", "grill-blueprint", "spec"]
    assert result.gate == "spec-approval"


def test_auto_stops_on_grill_block(tmp_path):
    """A BLOCK verdict at the grill-blueprint gate halts the chain for review."""
    ws = _ws(tmp_path, [])
    calls = []
    result = hermes.run_hermes(
        "build it", ws, auto=True, execute=_chain_exec(calls, grill="BLOCK"),
        make_runner=lambda: FakeRunner(),
    )
    assert calls[-1] == "grill-blueprint"   # stopped at the gate
    assert "spec" not in calls              # never reached spec
    assert result.gate == "grill-blocked"


def test_grill_missing_verdict_blocks(tmp_path):
    """No VERDICT line at a grill gate defaults to BLOCK (skeptical)."""
    ws = _ws(tmp_path, [])
    calls = []

    def _exec(stage_name, workspace, agent=None):
        calls.append(stage_name)
        from cli.pipeline import load_stage

        st = load_stage(stage_name)
        if st and not st.artifact.endswith("/"):
            p = workspace / st.artifact
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        return AgentResult(ok=True, output="done")  # no VERDICT anywhere

    result = hermes.run_hermes(
        "build it", ws, auto=True, execute=_exec, make_runner=lambda: FakeRunner(),
    )
    assert result.gate == "grill-blocked"
    assert calls[-1] == "grill-blueprint"


def test_auto_stops_on_verify_fail(tmp_path):
    # Seed through tasks INCLUDING the grill gate reports so the chain reaches verify.
    ws = _ws(
        tmp_path,
        ["research.md", "proposals.md", "architecture.md", "spec.md", "tasks.md"],
    )
    (ws / "grill").mkdir()
    (ws / "grill" / "blueprint.md").write_text("VERDICT: READY")
    (ws / "grill" / "spec.md").write_text("VERDICT: READY")
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


# --------------------------- grill verdict parsing (per-axis safe) --------------------------- #
def test_grill_ready_reads_final_verdict():
    assert hermes._grill_ready("FINDING | LOW | x | nit\nVERDICT: READY") is True
    assert hermes._grill_ready("FINDING | CRITICAL | x | bug\nVERDICT: BLOCK") is False


def test_grill_ready_defaults_block_when_silent():
    assert hermes._grill_ready("no verdict line here") is False  # skeptical default


def test_grill_ready_ignores_per_axis_lines():
    # Per-axis scoring emits `AXIS | <name> | PASS|FAIL` lines BEFORE the overall
    # verdict. These must not be mistaken for the verdict — only the final
    # `VERDICT:` line decides. A passing per-axis set with a BLOCK overall = BLOCK.
    out = (
        "AXIS | testability | PASS\n"
        "AXIS | edge-cases | FAIL | no error path for empty input\n"
        "FINDING | HIGH | criteria | acceptance criterion not falsifiable\n"
        "VERDICT: BLOCK"
    )
    assert hermes._grill_ready(out) is False
    # All axes pass → overall READY still comes from the final line.
    ok = (
        "AXIS | testability | PASS\n"
        "AXIS | edge-cases | PASS\n"
        "VERDICT: READY"
    )
    assert hermes._grill_ready(ok) is True


def test_stage_routes_model_reaches_runner_factory(tmp_path):
    models_seen = []

    def make_runner(model=None):
        models_seen.append(model)
        return None

    def execute(stage, workspace, agent=None, prompt_prefix=""):
        return AgentResult(ok=True, output="done")

    result = hermes.run_hermes(
        "continue", tmp_path,
        execute=execute, make_runner=make_runner,
        stage_routes={"research": "sonnet"},
    )
    assert result.ok
    # The intent-route call uses an unrouted runner (None); the stage-execute
    # runner is routed to the mapped tier.
    assert "sonnet" in models_seen


def test_stage_routes_tolerates_zero_arg_factory(tmp_path):
    # Existing callers/tests pass factories with no `model` kwarg — routing
    # must degrade to an unrouted runner, never crash.
    def execute(stage, workspace, agent=None, prompt_prefix=""):
        return AgentResult(ok=True, output="done")

    result = hermes.run_hermes(
        "continue", tmp_path,
        execute=execute, make_runner=lambda: None,
        stage_routes={"research": "sonnet"},
    )
    assert result.ok


def test_no_stage_routes_is_byte_identical_default(tmp_path):
    calls = []

    def make_runner(model=None):
        calls.append(model)
        return None

    def execute(stage, workspace, agent=None, prompt_prefix=""):
        return AgentResult(ok=True, output="done")

    hermes.run_hermes("continue", tmp_path, execute=execute, make_runner=make_runner)
    assert all(m is None for m in calls)
