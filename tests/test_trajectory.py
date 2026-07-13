"""Tests for cli/trajectory — pure step build/append/read + summary projection."""

from __future__ import annotations

from cli.trajectory import (
    TrajectoryStep,
    append_step,
    build_step,
    efficiency_report,
    make_sink,
    read_steps,
    summarize,
    trajectory_path,
)


def test_build_step_passes_ts():
    step = build_step({"role": "implementer", "ok": True, "model": "sonnet"}, ts="2026-06-26T10:00:00")
    assert step.role == "implementer"
    assert step.ok is True
    assert step.model == "sonnet"
    assert step.ts == "2026-06-26T10:00:00"


def test_append_and_read_roundtrip(tmp_path):
    append_step(tmp_path, build_step({"role": "verifier", "ok": False}, ts="t1"))
    append_step(tmp_path, build_step({"role": "implementer", "ok": True}, ts="t2"))
    steps = read_steps(tmp_path)
    assert [s.role for s in steps] == ["verifier", "implementer"]
    assert [s.ok for s in steps] == [False, True]


def test_read_missing_file_is_empty(tmp_path):
    assert read_steps(tmp_path) == []


def test_read_skips_corrupt_lines(tmp_path):
    path = trajectory_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"role": "a", "ok": true}\nnot json\n{"role": "b", "ok": false}\n')
    steps = read_steps(tmp_path)
    assert [s.role for s in steps] == ["a", "b"]


def test_summarize_projection():
    steps = [
        TrajectoryStep(role="implementer", model="sonnet", ok=True, duration_s=1.0, ts="t1"),
        TrajectoryStep(role="verifier", model="haiku", ok=True, duration_s=2.0, ts="t2"),
        TrajectoryStep(role="verifier", model="haiku", ok=False, duration_s=0.5, ts="t3"),
    ]
    summary = summarize(steps)
    assert summary.total == 3
    assert summary.failures == 1
    assert summary.by_role["verifier"] == 2
    assert summary.total_duration_s == 3.5


def test_summarize_empty():
    summary = summarize([])
    assert summary.total == 0
    assert summary.failures == 0


def test_make_sink_writes_steps(tmp_path):
    """make_sink returns a callable that appends each step dict with a stamped ts."""
    sink = make_sink(tmp_path, ts="2026-06-26T12:00:00")
    sink({"role": "implementer", "ok": True})
    sink({"role": "verifier", "ok": False})
    steps = read_steps(tmp_path)
    assert len(steps) == 2
    assert all(s.ts == "2026-06-26T12:00:00" for s in steps)


def test_make_sink_failsafe_on_bad_dir(tmp_path):
    """A sink whose target can't be written must not raise (best-effort)."""
    # Point at a path whose parent is a file → mkdir/write fails internally.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    sink = make_sink(blocker / "sub", ts="t")
    # Should swallow the error, not raise.
    sink({"role": "x", "ok": True})


# --------------------------- efficiency_report (real data only) --------------------------- #
def test_efficiency_report_empty():
    out = efficiency_report([])
    assert "No trajectory data yet" in out


def test_efficiency_report_cycle_pass_rate():
    steps = [
        TrajectoryStep(role="cycle", ok=True, ts="t1"),
        TrajectoryStep(role="cycle", ok=True, ts="t2"),
        TrajectoryStep(role="cycle", ok=False, ts="t3"),
    ]
    out = efficiency_report(steps)
    assert "Cycle pass rate: 67%" in out
    assert "2/3 verified cycles" in out


def test_efficiency_report_no_cycle_steps():
    steps = [TrajectoryStep(role="implementer", ok=True, ts="t1")]
    out = efficiency_report(steps)
    assert "No completed loop cycles recorded yet" in out


def test_efficiency_report_escalation_rate():
    steps = [
        TrajectoryStep(role="implementer", ok=True, ts="t1"),
        TrajectoryStep(role="implementer", ok=True, ts="t2"),
        TrajectoryStep(role="logic", ok=True, ts="t3"),
        TrajectoryStep(role="advisor", ok=True, ts="t4"),
    ]
    out = efficiency_report(steps)
    assert "Escalation rate: 100%" in out
    assert "2 logic/advisor/test-writer/simplifier step(s) per 2 implementer step(s)" in out


def test_efficiency_report_no_implementer_steps():
    steps = [TrajectoryStep(role="cycle", ok=True, ts="t1")]
    out = efficiency_report(steps)
    assert "escalation rate not computable" in out


def test_efficiency_report_crash_rate_distinct_from_verify_fail():
    steps = [
        TrajectoryStep(role="implementer", ok=True, ts="t1"),
        TrajectoryStep(role="verifier", ok=True, ts="t2"),  # VERDICT: FAIL still exits 0
        TrajectoryStep(role="verifier", ok=False, ts="t3"),  # a real subprocess crash
    ]
    out = efficiency_report(steps)
    assert "Crash rate: 33%" in out
    assert "NOT verification failure" in out


def test_efficiency_report_never_claims_token_savings():
    # Without measured telemetry, the report must keep the honest caveat and
    # never fabricate a token number (the original law, new wording).
    steps = [TrajectoryStep(role="cycle", ok=True, ts="t1")]
    out = efficiency_report(steps)
    assert "No measured token data yet" in out
    assert "Measured tokens" not in out


def test_build_step_maps_measured_usage():
    step = build_step({"role": "implementer", "input_tokens": 10, "output_tokens": 5,
                       "cache_read_tokens": 70, "cache_creation_tokens": 3, "cost_usd": 0.02})
    assert step.input_tokens == 10
    assert step.output_tokens == 5
    assert step.cache_read_tokens == 70
    assert step.cache_creation_tokens == 3
    assert step.cost_usd == 0.02


def test_build_step_without_usage_leaves_none():
    step = build_step({"role": "implementer"})
    assert step.input_tokens is None
    assert step.output_tokens is None
    assert step.cost_usd is None


def test_counting_sink_accumulates_tokens_and_forwards():
    from cli.trajectory import counting_sink

    forwarded = []
    sink, totals = counting_sink(forwarded.append)
    sink({"role": "implementer", "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01})
    sink({"role": "verifier", "input_tokens": 20, "cache_read_tokens": 30})
    sink({"role": "logic"})  # no telemetry — contributes nothing
    assert len(forwarded) == 3
    assert totals["tokens"] == 200
    assert totals["cost_usd"] == 0.01


def test_efficiency_report_shows_measured_tokens_when_present():
    steps = [
        build_step({"role": "implementer", "ok": True, "input_tokens": 100, "output_tokens": 50}),
        build_step({"role": "cycle", "ok": True}),
    ]
    report = efficiency_report(steps)
    assert "Measured tokens: 150" in report
    assert "intentionally omitted" not in report


def test_efficiency_report_keeps_caveat_without_measurements():
    steps = [build_step({"role": "implementer", "ok": True})]
    report = efficiency_report(steps)
    assert "No measured token data yet" in report
