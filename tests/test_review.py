"""Tests for cli/review (pure) + cli/review_run (orchestration with fakes)."""

from __future__ import annotations

import pytest

from cli import review as rv
from cli.runner import AgentResult

SAMPLE_DIFF = """diff --git a/src/model.py b/src/model.py
index 111..222 100644
--- a/src/model.py
+++ b/src/model.py
@@ -1,3 +1,4 @@
 import numpy as np
+from sklearn.model_selection import train_test_split
 def train(): pass
diff --git a/src/agent_loop.py b/src/agent_loop.py
index 333..444 100644
--- a/src/agent_loop.py
+++ b/src/agent_loop.py
@@ -1 +1,2 @@
+while True: pass
"""


# --------------------------------------------------------------------------- #
# Change-set parsing + domain inference
# --------------------------------------------------------------------------- #
def test_parse_changed_files():
    files = rv.parse_changed_files(SAMPLE_DIFF)
    assert files == ["src/model.py", "src/agent_loop.py"]


def test_parse_handles_deletion():
    diff = (
        "diff --git a/old.py b/old.py\n"
        "deleted file mode 100644\n"
        "--- a/old.py\n+++ /dev/null\n"
    )
    assert rv.parse_changed_files(diff) == ["old.py"]


def test_build_change_set_empty():
    cs = rv.build_change_set("")
    assert cs.is_empty


def test_infer_domains_from_paths():
    assert "ai-agent-engineering" in rv.infer_domains(["src/agent_loop.py"])
    assert "nlp" in rv.infer_domains(["pkg/tokenizer.py"])


def test_infer_domains_fallback():
    assert rv.infer_domains(["README.md"]) == [rv.DEFAULT_DOMAIN]


# --------------------------------------------------------------------------- #
# Findings parsing + aggregation + gate
# --------------------------------------------------------------------------- #
def test_parse_findings_strict_grammar():
    out = (
        "Some prose.\n"
        "FINDING | HIGH | src/model.py:12 | data leak: target in features\n"
        "FINDING | low | - | minor naming\n"
        "garbage line\n"
        "VERDICT: FAIL\n"
    )
    findings = rv.parse_findings("ml-logic", out)
    assert len(findings) == 2
    assert findings[0].severity == "HIGH"
    assert findings[0].file == "src/model.py"
    assert findings[0].line == 12
    assert findings[1].severity == "LOW"
    assert findings[1].file == ""


def test_parse_findings_unknown_severity_becomes_medium():
    findings = rv.parse_findings("code", "FINDING | WAT | a.py:1 | x\n")
    assert findings[0].severity == "MEDIUM"


def test_aggregate_dedupes_across_axes():
    f1 = rv.Finding("code", "HIGH", "a.py", 1, "same issue")
    f2 = rv.Finding("ml-logic", "HIGH", "a.py", 1, "Same Issue")  # dup (case-insensitive)
    f3 = rv.Finding("code", "LOW", "b.py", 2, "other")
    r1 = rv.AxisResult("code", ran=True, findings=[f1, f3])
    r2 = rv.AxisResult("ml-logic", ran=True, findings=[f2])
    merged = rv.aggregate([r1, r2])
    assert len(merged) == 2  # f1/f2 deduped
    assert merged[0].severity == "HIGH"  # severity-ordered


def test_gate_fails_on_blocking_finding():
    r = rv.AxisResult("code", ran=True, findings=[rv.Finding("code", "CRITICAL", "a.py", 1, "x")])
    clean = rv.AxisResult("ml-logic", ran=True, findings=[])
    clean2 = rv.AxisResult("system-logic", ran=True, findings=[])
    decision = rv.gate([r, clean, clean2])
    assert not decision.passed
    assert len(decision.blocking) == 1


def test_gate_passes_with_only_low_medium():
    rs = [
        rv.AxisResult("code", ran=True, findings=[rv.Finding("code", "LOW", "a.py", 1, "x")]),
        rv.AxisResult("ml-logic", ran=True, findings=[]),
        rv.AxisResult("system-logic", ran=True, findings=[rv.Finding("system-logic", "MEDIUM", "b.py", 2, "y")]),
    ]
    assert rv.gate(rs).passed


def test_gate_fails_on_inconclusive_axis():
    rs = [
        rv.AxisResult("code", ran=True, findings=[]),
        rv.AxisResult("ml-logic", ran=False, error="agent died"),
        rv.AxisResult("system-logic", ran=True, findings=[]),
    ]
    decision = rv.gate(rs)
    assert not decision.passed
    assert "ml-logic" in decision.inconclusive_axes


# --------------------------------------------------------------------------- #
# Prompt building
# --------------------------------------------------------------------------- #
def test_build_axis_prompt_injects_context():
    cs = rv.build_change_set(SAMPLE_DIFF, source="pr", ref="42")
    prompt = rv.build_axis_prompt(
        "ml-logic", cs,
        profile_text="## ML-logic invariants\n- no leakage",
        recall_block="--- past lessons ---\n- watch splits",
        staleness_banner="⚠ stale",
        logic_evaluator_text="check data leakage",
    )
    assert "⚠ stale" in prompt
    assert "past lessons" in prompt
    assert "no leakage" in prompt
    assert "check data leakage" in prompt
    assert "FINDING |" in prompt
    assert "src/model.py" in prompt


def test_build_axis_prompt_minimal_no_optional_blocks():
    cs = rv.build_change_set(SAMPLE_DIFF)
    prompt = rv.build_axis_prompt("code", cs)
    # Fail-safe: no profile / recall / staleness → still a coherent prompt.
    assert "FINDING |" in prompt
    assert "logic profile" not in prompt


def test_build_axis_prompt_logic_eval_only_for_ml_axis():
    cs = rv.build_change_set(SAMPLE_DIFF)
    p = rv.build_axis_prompt("code", cs, logic_evaluator_text="should not appear")
    assert "should not appear" not in p


def test_build_axis_prompt_rejects_unknown_axis():
    cs = rv.build_change_set(SAMPLE_DIFF)
    with pytest.raises(ValueError):
        rv.build_axis_prompt("nonsense", cs)


def test_ensure_distinct_axes():
    a, b, c = object(), object(), object()
    rv.ensure_distinct_axes([a, b, c])  # ok
    with pytest.raises(ValueError):
        rv.ensure_distinct_axes([a, b, a])


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #
def test_render_report_pass():
    cs = rv.build_change_set(SAMPLE_DIFF)
    rs = [rv.AxisResult(ax, ran=True, findings=[]) for ax in rv.AXES]
    decision = rv.gate(rs)
    report = rv.render_report(cs, rs, decision, ["nlp"])
    assert "✅ PASS" in report
    assert "Axis coverage" in report


def test_render_pr_comment_with_blocking():
    decision = rv.Gate(passed=False, blocking=[rv.Finding("code", "HIGH", "a.py", 1, "bug")])
    comment = rv.render_pr_comment(rv.build_change_set(SAMPLE_DIFF, source="pr", ref="7"), decision)
    assert "❌ FAIL" in comment
    assert "a.py:1" in comment


# --------------------------------------------------------------------------- #
# Orchestration (cli/review_run) with fakes
# --------------------------------------------------------------------------- #
class FakeRunner:
    """Stands in for AgentRunner: returns a canned reply per axis prompt."""

    def __init__(self, reply: str, ok: bool = True):
        self.reply = reply
        self.ok = ok

    def run(self, prompt: str, cwd=None) -> AgentResult:
        if not self.ok:
            return AgentResult(ok=False, output="", error="boom")
        return AgentResult(ok=True, output=self.reply)


def _fake_cmd_runner(diff_text: str):
    """Build a subprocess.run stand-in that returns `diff_text` for git/gh."""
    class Proc:
        returncode = 0
        stdout = diff_text
        stderr = ""

    def runner(argv, **kwargs):
        return Proc()

    return runner


def test_run_review_empty_diff_skips(tmp_path):
    from cli import review_run

    res = review_run.run_review(
        target=None, root=tmp_path, skills_dir=tmp_path / "skills",
        make_runner=lambda: FakeRunner("VERDICT: PASS"),
        cmd_runner=_fake_cmd_runner(""),
    )
    assert res.ok
    assert res.skipped_reason


def test_run_review_pass_writes_report(tmp_path):
    from cli import review_run

    skills = tmp_path / "skills"
    res = review_run.run_review(
        target=None, root=tmp_path, skills_dir=skills,
        make_runner=lambda: FakeRunner("FINDING | LOW | x.py:1 | nit\nVERDICT: PASS"),
        reviews_dir=tmp_path / "reviews",
        cmd_runner=_fake_cmd_runner(SAMPLE_DIFF),
        ts="2026-06-19T10:00:00",
    )
    assert res.ok
    assert res.gate.passed
    assert res.report_path.exists()
    # Cost row recorded.
    assert (tmp_path / "sigma" / "costs.jsonl").exists()


def test_run_review_blocking_ratchets(tmp_path):
    from cli import review_run

    skills = tmp_path / "skills"
    res = review_run.run_review(
        target=None, root=tmp_path, skills_dir=skills,
        make_runner=lambda: FakeRunner(
            "FINDING | CRITICAL | src/model.py:2 | target leakage\nVERDICT: FAIL"
        ),
        reviews_dir=tmp_path / "reviews",
        cmd_runner=_fake_cmd_runner(SAMPLE_DIFF),
        ts="2026-06-19T10:00:00",
    )
    assert not res.gate.passed
    # Each axis reports the finding → deduped to one blocking finding → one ratchet.
    assert len(res.ratcheted) >= 1
    assert all(p.exists() for p in res.ratcheted)


def test_run_review_inconclusive_axis_fails(tmp_path):
    from cli import review_run

    # A runner factory that fails: every axis is inconclusive.
    res = review_run.run_review(
        target=None, root=tmp_path, skills_dir=tmp_path / "skills",
        make_runner=lambda: FakeRunner("", ok=False),
        reviews_dir=tmp_path / "reviews",
        cmd_runner=_fake_cmd_runner(SAMPLE_DIFF),
        ts="2026-06-19T10:00:00",
    )
    assert not res.gate.passed
    assert res.gate.inconclusive_axes
