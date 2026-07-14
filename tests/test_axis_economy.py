"""Tests for cli/axis_economy.py — the per-axis token-economy report.

One test per BDD scenario in sigma/specs/2026-07-14-axis-economy/spec.md, plus the
record_cycle_steps effect-field wiring. All pure — hand-built TrajectoryStep lists,
no agents.
"""

from __future__ import annotations

from cli.axis_economy import AxisEconomy, build_economy
from cli.trajectory import TrajectoryStep, build_step


def _measured(role, tokens, ts):
    """A non-cycle agent step carrying real telemetry."""
    return TrajectoryStep(role=role, ok=True, ts=ts, input_tokens=tokens, output_tokens=0)


def _cycle(ts, **flags):
    """A synthetic role='cycle' marker with per-axis effect flags."""
    return TrajectoryStep(role="cycle", ok=flags.pop("ok", True), ts=ts, **flags)


def _row(economy: AxisEconomy, role: str):
    return next((r for r in economy.rows if r.role == role), None)


def _review_section(report: str) -> str:
    """The '## Review' block only (candidates live here, earning axes must not)."""
    if "## Earning" in report:
        return report.split("## Earning", 1)[0]
    return report


# --- Scenario: economy report flags an idle expensive axis ------------------- #
def test_idle_expensive_axis_is_flagged():
    steps = [
        _measured("logic", 5000, "t1"),
        _measured("logic", 5000, "t2"),
        _cycle("c1", logic_ok=True),   # logic ran, never caught a fail
        _cycle("c2", logic_ok=True),
    ]
    economy = build_economy(steps)
    logic = _row(economy, "logic")
    assert logic is not None
    assert logic.token_total == 10000
    assert logic.value_events == 0
    assert logic.flag and "prune candidate" in logic.flag
    # It renders in the review section with its token total.
    report = economy.render()
    assert "logic" in report
    assert "10,000" in report
    assert "prune candidate" in report


# --- Scenario: economy report credits a productive axis ---------------------- #
def test_productive_axis_is_credited_not_flagged():
    steps = [
        _measured("advisor", 8000, "t1"),
        _cycle("c1", advised=True),    # advisor rescued a cycle
        _cycle("c2", advised=False),
    ]
    economy = build_economy(steps)
    advisor = _row(economy, "advisor")
    assert advisor is not None
    assert advisor.value_events == 1
    assert advisor.flag is None
    assert advisor.roi == 8000.0
    report = economy.render()
    assert "advisor" in report
    # advisor must not appear as a prune candidate in the review section
    assert "prune candidate" not in _review_section(report)


# --- Scenario: core axes are never flagged ----------------------------------- #
def test_core_axes_never_flagged():
    steps = [
        _measured("implementer", 3000, "t1"),
        _measured("verifier", 3000, "t2"),
        _cycle("c1"),
        _cycle("c2"),
    ]
    economy = build_economy(steps)
    impl = _row(economy, "implementer")
    verifier = _row(economy, "verifier")
    assert impl.is_core and impl.flag is None
    assert verifier.is_core and verifier.flag is None
    # core axes earn on every cycle
    assert impl.value_events == 2
    assert verifier.value_events == 2


# --- Scenario: unmeasured axis is not estimated ------------------------------ #
def test_unmeasured_axis_is_not_estimated():
    steps = [
        # logic ran but the step carries NO telemetry (codex axis / telemetry off)
        TrajectoryStep(role="logic", ok=True, ts="t1"),
        _cycle("c1", logic_ok=True),
    ]
    economy = build_economy(steps)
    logic = _row(economy, "logic")
    assert logic.measured is False
    assert logic.token_total is None      # never invented
    assert logic.roi is None              # excluded from ROI ranking
    assert logic.flag is None             # not flagged (no token evidence)
    report = economy.render()
    assert "unmeasured" in report


# --- Scenario: empty trajectory is safe -------------------------------------- #
def test_empty_trajectory_is_safe():
    economy = build_economy([])
    assert economy.rows == []
    assert economy.cycles == 0
    report = economy.render()
    assert "No trajectory data yet" in report


# --- Scenario: old trajectory without effect fields still reads -------------- #
def test_old_trajectory_without_effect_fields_degrades():
    # Simulate a pre-effect-fields JSONL row: dict has role but none of the new flags.
    old_cycle = build_step({"role": "cycle", "ok": True, "ts": "c1"})
    assert old_cycle.logic_ok is None
    assert old_cycle.advised is None
    steps = [_measured("logic", 4000, "t1"), old_cycle]
    # Must not raise; the value tally degrades to zero.
    economy = build_economy(steps)
    logic = _row(economy, "logic")
    assert logic.value_events == 0
    # And since it spent tokens with zero value, it is (correctly) flagged.
    assert logic.flag is not None


def test_garbage_effect_field_degrades_to_none():
    # A hand-edited row with a non-bool logic_ok must parse to None, never raise.
    step = build_step({"role": "cycle", "ok": True, "logic_ok": "yes", "ts": "c1"})
    assert step.logic_ok is None


# --- Scenario: JSON output composes with economy (shape) --------------------- #
def test_economy_dataclass_is_json_shaped():
    from dataclasses import asdict

    steps = [_measured("logic", 5000, "t1"), _cycle("c1", logic_ok=True)]
    economy = build_economy(steps)
    d = asdict(economy)
    assert set(d) == {"rows", "total_measured_tokens", "cycles"}
    assert isinstance(d["rows"], list)
    assert d["total_measured_tokens"] == 5000
    assert d["cycles"] == 1


# --- R8: division-by-zero guard (tokens, zero cycles) ------------------------ #
def test_axis_with_tokens_but_zero_cycles_does_not_divide_by_zero():
    steps = [_measured("logic", 5000, "t1")]  # no cycle steps at all
    economy = build_economy(steps)
    logic = _row(economy, "logic")
    assert logic.roi == 5000.0   # max(0, 1) guard → divides by 1
    assert economy.cycles == 0


# --- R5: unmeasured + zero value must not TypeError on None > 0 --------------- #
def test_unmeasured_zero_value_axis_does_not_raise_on_flag_check():
    # logic has cycle evidence of zero value but NO token telemetry: the flag check
    # must short-circuit on `measured` before comparing None > 0.
    steps = [
        TrajectoryStep(role="logic", ok=True, ts="t1"),  # unmeasured
        _cycle("c1", logic_ok=True),
    ]
    economy = build_economy(steps)  # would raise TypeError if order were wrong
    logic = _row(economy, "logic")
    assert logic.flag is None


# --- T2: record_cycle_steps stamps the effect flags -------------------------- #
def test_record_cycle_steps_carries_effect_flags():
    from cli.loop import CycleOutcome, record_cycle_steps

    captured = []
    outcome = CycleOutcome(
        task_title="t", implemented=True, verified=True,
        logic_ok=False, advised=True, e2e_ok=False, simplified=True, test_written=True,
        domain="nlp",
    )
    record_cycle_steps([outcome], captured.append)
    assert len(captured) == 1
    step = captured[0]
    assert step["role"] == "cycle"
    assert step["logic_ok"] is False
    assert step["advised"] is True
    assert step["e2e_ok"] is False
    assert step["simplified"] is True
    assert step["test_written"] is True
