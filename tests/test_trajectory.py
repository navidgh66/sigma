"""Tests for cli/trajectory — pure step build/append/read + summary projection."""

from __future__ import annotations

from cli.trajectory import (
    TrajectoryStep,
    append_step,
    build_step,
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
