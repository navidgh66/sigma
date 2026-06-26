"""Tests for cli/eval_run — orchestration with fake runners (no real agents)."""

from __future__ import annotations

from cli.eval_run import eval_set_path, run_eval
from cli.runner import AgentResult, AgentRunner

SET = """# Eval set: demo

## case: c1
input: do the thing
rubric: thing is done

## case: c2
input: do other thing
rubric: other thing is done
"""


class FakeRunner(AgentRunner):
    """Returns a fixed result; records prompts + role."""

    def __init__(self, output="VERDICT: PASS", ok=True):
        super().__init__()
        self._output = output
        self._ok = ok
        self.calls = []

    def available(self):
        return True

    def run(self, prompt, cwd=None, role="agent"):
        self.calls.append((role, prompt))
        return AgentResult(ok=self._ok, output=self._output)


def _write_set(tmp_path, body=SET, name="demo"):
    p = eval_set_path(tmp_path, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def test_run_eval_missing_set(tmp_path):
    res = run_eval("nope", tmp_path, make_sut=FakeRunner, make_grader=FakeRunner)
    assert res.ok is False
    assert "no eval set" in (res.error or "")


def test_run_eval_all_pass(tmp_path):
    _write_set(tmp_path)
    res = run_eval(
        "demo", tmp_path,
        make_sut=lambda: FakeRunner("produced output"),
        make_grader=lambda: FakeRunner("VERDICT: PASS"),
        threshold=0.8,
    )
    assert res.ok is True
    assert res.gate.passed is True
    assert res.report_path and res.report_path.exists()


def test_run_eval_fails_below_threshold(tmp_path):
    _write_set(tmp_path)
    res = run_eval(
        "demo", tmp_path,
        make_sut=lambda: FakeRunner("output"),
        make_grader=lambda: FakeRunner("VERDICT: FAIL"),
        threshold=0.8,
    )
    assert res.ok is True
    assert res.gate.passed is False


def test_run_eval_artifact_mode_skips_sut(tmp_path):
    _write_set(tmp_path)
    artifact = tmp_path / "spec.md"
    artifact.write_text("the spec body")
    sut_calls = []

    def make_sut():
        r = FakeRunner()
        sut_calls.append(r)
        return r

    res = run_eval(
        "demo", tmp_path,
        make_sut=make_sut,
        make_grader=lambda: FakeRunner("VERDICT: PASS"),
        artifact=artifact,
    )
    assert res.ok is True
    # Artifact mode must NOT invoke the system-under-test.
    assert sut_calls == []
    assert res.gate.passed is True


def test_run_eval_judge_uses_distinct_role(tmp_path):
    _write_set(tmp_path)
    seen_roles = []

    class RoleRunner(FakeRunner):
        def run(self, prompt, cwd=None, role="agent"):
            seen_roles.append(role)
            return AgentResult(ok=True, output="VERDICT: PASS")

    run_eval(
        "demo", tmp_path,
        make_sut=RoleRunner,
        make_grader=RoleRunner,
        threshold=0.5,
    )
    assert "eval-sut" in seen_roles
    assert "eval-judge" in seen_roles


def test_run_eval_records_cost(tmp_path):
    _write_set(tmp_path)
    run_eval(
        "demo", tmp_path,
        make_sut=lambda: FakeRunner("o"),
        make_grader=lambda: FakeRunner("VERDICT: PASS"),
        ts="2026-06-26T10:00:00",
    )
    ledger = tmp_path / "sigma" / "costs.jsonl"
    assert ledger.exists()
    assert "eval" in ledger.read_text()


def test_run_eval_empty_set(tmp_path):
    _write_set(tmp_path, body="# Eval set: empty\n", name="demo")
    res = run_eval("demo", tmp_path, make_sut=FakeRunner, make_grader=FakeRunner)
    assert res.ok is True
    assert res.skipped_reason and "no cases" in res.skipped_reason
