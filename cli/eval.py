"""Pure logic for `sigma eval` — run an eval set, LM-judge each case, gate.

The Google "New SDLC" paper's strongest prescription for engineering leaders is
*set the bar at the eval, not the demo*: a working demo proves an agent can
succeed once; a passing eval suite proves it succeeds reliably. Evals — labelled
cases scored by a rubric — are how intent is communicated to an agent and how
non-deterministic output is verified (the half that tests can't cover).

This module owns everything testable without a real agent:
  - `parse_eval_set` — a simple, documented markdown format → `EvalCase`s;
  - `build_grade_prompt` — the LM-judge prompt (case + actual output + criteria);
  - `parse_grade` — skeptical verdict parse (missing `VERDICT: PASS` → FAIL, same
    default-deny as the loop/review);
  - `aggregate` / `gate` / `render_report` — fold case results into a pass rate,
    decide against a threshold (default 0.8 — the paper's 80% bar), render.
  - `ensure_distinct` — the system-under-test runner and the grader MUST be
    distinct agents (maker≠grader, the review/loop law) — `ValueError` on reuse.

The subprocess wiring (run SUT, fan grading out in parallel, write the report,
cost + ratchet) lives in `cli/eval_run.py`. Pure + deterministic here: no
subprocess, no clock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# The paper's "80% problem" framing makes 0.8 the natural default bar.
DEFAULT_THRESHOLD = 0.8

_CASE_HEADER_RE = re.compile(r"^##\s*case:\s*(?P<id>.+?)\s*$", re.IGNORECASE)
_FIELD_RE = re.compile(r"^(?P<key>input|expected|rubric|domain)\s*:\s*(?P<val>.*)$", re.IGNORECASE)


@dataclass
class EvalCase:
    id: str
    input: str
    expected: Optional[str] = None
    rubric: Optional[str] = None
    domain: Optional[str] = None

    def criteria(self) -> str:
        """The grading criteria: explicit expected output and/or a rubric."""
        parts = []
        if self.expected:
            parts.append(f"Expected output: {self.expected}")
        if self.rubric:
            parts.append(f"Rubric: {self.rubric}")
        return "\n".join(parts) or "(no explicit criteria — judge for correctness and quality)"


@dataclass
class EvalReport:
    total: int
    passed: int
    failed: int
    results: List[Tuple[str, bool, str]] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


@dataclass
class EvalGate:
    passed: bool
    reason: str
    pass_rate: float
    threshold: float


def parse_eval_set(text: str) -> List[EvalCase]:
    """Parse the markdown eval-set format into cases.

    Format (one block per case):

        ## case: <id>
        domain: <domain>          # optional
        input: <the input/task>
        expected: <expected output>   # optional
        rubric: <grading rubric>      # optional (expected and/or rubric)

    A line that is not a recognized `key: value` after a case header is appended
    to the most recently seen field (so inputs/rubrics may span lines). Lenient:
    a case with no fields still parses (id only).
    """
    cases: List[EvalCase] = []
    cur: Optional[dict] = None
    last_key: Optional[str] = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            cases.append(
                EvalCase(
                    id=cur["id"],
                    input=cur.get("input", "").strip(),
                    expected=(cur.get("expected") or "").strip() or None,
                    rubric=(cur.get("rubric") or "").strip() or None,
                    domain=(cur.get("domain") or "").strip() or None,
                )
            )
        cur = None

    for line in text.splitlines():
        header = _CASE_HEADER_RE.match(line)
        if header:
            flush()
            cur = {"id": header.group("id").strip()}
            last_key = None
            continue
        if cur is None:
            continue
        field_match = _FIELD_RE.match(line.strip())
        if field_match:
            key = field_match.group("key").lower()
            cur[key] = field_match.group("val")
            last_key = key
        elif last_key and line.strip():
            # Continuation line for the previous field (multi-line input/rubric).
            cur[last_key] = (cur.get(last_key, "") + "\n" + line).strip()
    flush()
    return cases


def build_grade_prompt(case: EvalCase, actual: str) -> str:
    """Build the LM-judge prompt that grades `actual` against the case's criteria."""
    return (
        "You are an EVAL JUDGE — a distinct agent from whatever produced the output "
        "below. Grade strictly and skeptically: pass ONLY if the actual output "
        "genuinely satisfies the criteria. A fluent answer that misses the criteria "
        "is a FAIL.\n\n"
        f"--- case: {case.id} ---\n"
        f"Input/task:\n{case.input}\n\n"
        f"Criteria:\n{case.criteria()}\n\n"
        f"--- actual output ---\n{actual}\n--- end ---\n\n"
        "Reply with exactly two lines:\n"
        "REASON: <one sentence>\n"
        "VERDICT: PASS  or  VERDICT: FAIL"
    )


def parse_grade(judge_output: str) -> Tuple[bool, str]:
    """Parse the judge's reply → (passed, reason). Missing verdict → FAIL (skeptical)."""
    passed = False
    reason = ""
    for line in judge_output.splitlines():
        s = line.strip()
        upper = s.upper()
        if upper.startswith("VERDICT:"):
            passed = "PASS" in upper
        elif upper.startswith("REASON:"):
            reason = s.split(":", 1)[1].strip()
    if not reason:
        reason = "passed" if passed else "no clear PASS verdict"
    return passed, reason


def aggregate(results: List[Tuple[str, bool, str]]) -> EvalReport:
    """Fold (case_id, passed, reason) tuples into a report."""
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    return EvalReport(total=total, passed=passed, failed=total - passed, results=list(results))


def gate(report: EvalReport, threshold: float = DEFAULT_THRESHOLD) -> EvalGate:
    """Decide pass/fail against a pass-rate threshold.

    An empty report (no cases ran) NEVER passes — a dead eval is not a silent
    success, the same skeptical stance as review's inconclusive axis.
    """
    if report.total == 0:
        return EvalGate(False, "no eval cases ran", 0.0, threshold)
    rate = report.pass_rate
    ok = rate >= threshold
    verb = "meets" if ok else "below"
    reason = f"pass rate {rate:.2f} {verb} threshold {threshold:.2f} ({report.passed}/{report.total})"
    return EvalGate(ok, reason, rate, threshold)


def ensure_distinct(sut, grader) -> None:
    """The system-under-test runner and the grader MUST be distinct agents.

    Same law as maker≠checker / the review axes — uses `is`, not `==`, because
    AgentRunner is a dataclass and two fresh instances compare equal.
    """
    if sut is grader:
        raise ValueError("eval system-under-test and grader must be distinct agents")


def render_report(report: EvalReport, decision: EvalGate, set_name: str) -> str:
    """Render the markdown eval report."""
    mark = "✅ PASS" if decision.passed else "❌ FAIL"
    lines = [
        f"# Eval report: {set_name}",
        "",
        f"**{mark}** — {decision.reason}",
        "",
        "## Cases",
        "",
    ]
    for case_id, ok, reason in report.results:
        symbol = "✓" if ok else "✗"
        lines.append(f"- {symbol} **{case_id}** — {reason}")
    return "\n".join(lines)
