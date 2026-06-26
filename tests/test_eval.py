"""Tests for cli/eval — pure eval-set parsing, grading, aggregation, gate."""

from __future__ import annotations

import pytest

from cli.eval import (
    DEFAULT_THRESHOLD,
    EvalCase,
    EvalReport,
    aggregate,
    build_grade_prompt,
    ensure_distinct,
    gate,
    parse_eval_set,
    parse_grade,
    render_report,
)

SAMPLE = """# Eval set: tokenizer

## case: splits-on-whitespace
domain: nlp
input: Tokenize "hello world"
expected: two tokens — "hello" and "world"

## case: handles-empty
input: Tokenize ""
rubric: returns an empty list, does not error
"""


def test_parse_eval_set_basic():
    cases = parse_eval_set(SAMPLE)
    assert len(cases) == 2
    assert cases[0].id == "splits-on-whitespace"
    assert cases[0].domain == "nlp"
    assert "hello world" in cases[0].input
    assert cases[0].expected and "two tokens" in cases[0].expected
    assert cases[1].id == "handles-empty"
    assert cases[1].rubric and "empty list" in cases[1].rubric


def test_parse_eval_set_empty():
    assert parse_eval_set("") == []
    assert parse_eval_set("# just a title\n") == []


def test_build_grade_prompt_includes_actual_and_criteria():
    case = EvalCase(id="c1", input="do x", expected="x is done", rubric=None, domain="nlp")
    prompt = build_grade_prompt(case, actual="here is x done")
    assert "do x" in prompt
    assert "x is done" in prompt
    assert "here is x done" in prompt
    assert "VERDICT:" in prompt


def test_parse_grade_skeptical():
    assert parse_grade("looks good\nVERDICT: PASS")[0] is True
    assert parse_grade("VERDICT: FAIL")[0] is False
    # Missing verdict → FAIL (skeptical default, like the loop/review).
    assert parse_grade("no verdict at all")[0] is False


def test_parse_grade_returns_reason():
    ok, reason = parse_grade("REASON: output matched\nVERDICT: PASS")
    assert ok is True
    assert "matched" in reason


def test_aggregate_counts_pass_fail():
    report = aggregate(
        [
            ("c1", True, "ok"),
            ("c2", False, "wrong"),
            ("c3", True, "ok"),
        ]
    )
    assert report.total == 3
    assert report.passed == 2
    assert report.failed == 1
    assert report.pass_rate == pytest.approx(2 / 3)


def test_aggregate_empty():
    report = aggregate([])
    assert report.total == 0
    assert report.pass_rate == 0.0


def test_gate_passes_at_threshold():
    report = EvalReport(total=10, passed=8, failed=2, results=[])
    decision = gate(report, threshold=0.8)
    assert decision.passed is True


def test_gate_fails_below_threshold():
    report = EvalReport(total=10, passed=7, failed=3, results=[])
    decision = gate(report, threshold=0.8)
    assert decision.passed is False
    assert "0.70" in decision.reason or "70" in decision.reason


def test_gate_empty_report_fails():
    # No cases run → never a silent pass (skeptical, like review's dead axis).
    decision = gate(EvalReport(total=0, passed=0, failed=0, results=[]), threshold=DEFAULT_THRESHOLD)
    assert decision.passed is False


def test_ensure_distinct_raises_on_reuse():
    shared = object()
    with pytest.raises(ValueError):
        ensure_distinct(shared, shared)


def test_ensure_distinct_ok():
    ensure_distinct(object(), object())  # no raise


def test_render_report_contains_cases():
    report = aggregate([("c1", True, "ok"), ("c2", False, "missed edge case")])
    decision = gate(report, threshold=0.8)
    text = render_report(report, decision, set_name="tokenizer")
    assert "tokenizer" in text
    assert "c1" in text
    assert "c2" in text
    assert "missed edge case" in text
