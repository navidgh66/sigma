"""Tests for cli/cost — estimate, calibrate, ledger I/O, report, fail-safe."""

from __future__ import annotations

from cli.cost import (
    TIER_CHEAP,
    TIER_MID,
    TIER_STRONG,
    append_ledger,
    build_record,
    calibrate,
    estimate,
    ledger_path,
    read_ledger,
    report,
    routing_for,
)


def test_estimate_static_when_no_ledger():
    est = estimate("review", units=6, rows=[])
    assert est.estimated_tokens > 0
    assert not est.calibrated
    assert est.units == 6


def test_estimate_zero_units():
    est = estimate("review", units=0, rows=[])
    assert est.estimated_tokens == 0


def test_estimate_clamps_negative_units():
    est = estimate("review", units=-5, rows=[])
    assert est.units == 0
    assert est.estimated_tokens == 0


def test_routing_review_axes():
    routes = routing_for("review")
    assert routes["code"] == TIER_CHEAP
    assert routes["ml-logic"] == TIER_STRONG


def test_loop_routing_includes_e2e_at_strong_tier():
    routes = routing_for("loop")
    assert routes["e2e"] == TIER_STRONG


def test_calibrate_from_ledger():
    rows = [
        {"op": "review", "units": 2, "tokens": 1000},
        {"op": "review", "units": 2, "tokens": 1400},
        {"op": "profile", "units": 5, "tokens": 50000},  # other op ignored
    ]
    factor = calibrate("review", rows)
    # mean of (500, 700) = 600
    assert factor == 600.0


def test_calibrate_skips_bad_rows():
    rows = [
        {"op": "review", "units": 0, "tokens": 100},     # zero units skipped
        {"op": "review", "units": 2, "tokens": "x"},      # non-numeric skipped
        {"op": "review", "units": 4, "tokens": 2000},     # → 500
    ]
    assert calibrate("review", rows) == 500.0


def test_calibrate_none_when_no_usable_rows():
    assert calibrate("review", []) is None
    assert calibrate("review", [{"op": "loop", "units": 1, "tokens": 1}]) is None


def test_estimate_uses_calibration_when_available():
    rows = [{"op": "review", "units": 1, "tokens": 999}]
    est = estimate("review", units=3, rows=rows)
    assert est.calibrated
    assert est.tokens_per_unit == 999.0
    assert est.estimated_tokens == 2997


def test_ledger_roundtrip(tmp_path):
    ledger = ledger_path(tmp_path)
    row = build_record("review", units=6, tokens=24000, ts="2026-06-19T10:00:00",
                       estimated=20000, models={"code": "haiku"})
    append_ledger(ledger, row)
    rows = read_ledger(ledger)
    assert len(rows) == 1
    assert rows[0]["op"] == "review"
    assert rows[0]["estimated"] == 20000


def test_read_ledger_missing_file(tmp_path):
    assert read_ledger(tmp_path / "nope.jsonl") == []


def test_read_ledger_skips_garbage(tmp_path):
    ledger = tmp_path / "costs.jsonl"
    ledger.write_text('{"op":"review","units":1,"tokens":10}\nNOT JSON\n\n[1,2,3]\n')
    rows = read_ledger(ledger)
    # Only the one valid dict line survives.
    assert len(rows) == 1
    assert rows[0]["op"] == "review"


def test_build_record_minimal():
    row = build_record("profile", units=10, tokens=30000, ts="2026-06-19T00:00:00")
    assert "estimated" not in row
    assert "models" not in row
    assert row["units"] == 10


def test_report_empty():
    out = report([])
    assert "No cost data yet" in out


def test_report_aggregates_and_shows_drift():
    rows = [
        {"op": "review", "units": 6, "tokens": 24000, "estimated": 20000},
        {"op": "review", "units": 6, "tokens": 26000, "estimated": 20000},
        {"op": "profile", "units": 10, "tokens": 30000},
    ]
    out = report(rows)
    assert "review" in out
    assert "profile" in out
    assert "est drift" in out


def test_calibrate_is_weighted_by_units():
    # One large run (100 units) + one small (2 units). Weighted = totals ratio.
    rows = [
        {"op": "review", "units": 100, "tokens": 400000},  # 4000/unit
        {"op": "review", "units": 2, "tokens": 10000},      # 5000/unit
    ]
    # Weighted: 410000 / 102 ≈ 4019.6 (not the unweighted mean 4500).
    factor = calibrate("review", rows)
    assert abs(factor - 410000 / 102) < 1e-6


def test_report_skips_zero_token_rows_from_run_count():
    rows = [
        {"op": "review", "units": 6, "tokens": 24000},
        {"op": "review", "units": 6, "tokens": 0},  # aborted/dry — must not count
    ]
    out = report(rows)
    assert "1 run(s)" in out


def test_routing_for_other_ops():
    assert routing_for("profile") == {"walk": "sonnet"}
    assert "logic" in routing_for("loop")
    assert routing_for("loop")["advisor"] == "opus"
    assert routing_for("research") == {"fan-out": "sonnet", "synthesis": "opus"}
    assert routing_for("unknown-op") == {}


def test_research_routing_includes_synthesis_at_strong_tier():
    routes = routing_for("research")
    assert routes["fan-out"] == TIER_MID
    assert routes["synthesis"] == TIER_STRONG


def test_estimate_render_includes_routing():
    est = estimate("review", units=6, rows=[])
    line = est.render()
    assert "cost estimate" in line
    assert "code→" in line


def test_routing_for_hermes_routes_planning_strong_execution_mid():
    routes = routing_for("hermes")
    for stage in ("propose", "blueprint", "grill-blueprint", "spec", "grill-spec", "tasks"):
        assert routes[stage] == TIER_STRONG, stage
    for stage in ("research", "implement-task", "verify", "loop"):
        assert routes[stage] == TIER_MID, stage


def test_routing_for_hermes_covers_every_pipeline_stage():
    from cli.pipeline import STAGE_NAMES

    assert set(routing_for("hermes")) == set(STAGE_NAMES)
