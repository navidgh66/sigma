"""`sigma eval` — run an eval set, grade each case with an LM judge, gate.

Wires the pure eval logic (`cli/eval.py`) to real subprocesses:

  - resolve the eval set file (sigma/evals/<name>.md);
  - PROMPT mode (default): run each case's input through a system-under-test
    runner, then grade the output with a DISTINCT judge runner;
  - ARTIFACT mode: grade an existing artifact's text against each case's rubric
    (no SUT run) — useful for grading a stage output (spec.md, a report);
  - fan grading out in PARALLEL through fresh judge runners (the CLI-only
    concurrency, like review);
  - aggregate → gate at a threshold → write sigma/evals/<name>/report.md;
  - cost estimate up front, recorded after; `--check` exits non-zero below bar.

The runner factory + cmd_runner are injectable, so the whole flow is testable
with fakes.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

from cli import eval as ev
from cli.cost import append_ledger, build_record, estimate, ledger_path, read_ledger
from cli.runner import AgentRunner


@dataclass
class EvalRunResult:
    ok: bool
    gate: Optional[ev.EvalGate] = None
    report: str = ""
    report_path: Optional[Path] = None
    set_name: str = ""
    error: Optional[str] = None
    skipped_reason: Optional[str] = None


def eval_set_path(root: Path, name: str) -> Path:
    """Where a named eval set lives for a project."""
    return root / "sigma" / "evals" / f"{name}.md"


def _grade_case(
    case: ev.EvalCase,
    actual: str,
    make_grader: Callable[[], AgentRunner],
    sut: Optional[AgentRunner],
    cwd: Path,
) -> Tuple[str, bool, str]:
    """Grade one case → (id, passed, reason). A grader failure → FAIL (skeptical)."""
    grader = make_grader()
    if sut is not None:
        ev.ensure_distinct(sut, grader)
    res = grader.run(ev.build_grade_prompt(case, actual), cwd=cwd, role="eval-judge")
    if not res.ok:
        return case.id, False, f"judge failed: {res.error or 'unknown'}"
    passed, reason = ev.parse_grade(res.output)
    return case.id, passed, reason


def run_eval(
    name: str,
    root: Path,
    make_sut: Callable[[], AgentRunner],
    make_grader: Callable[[], AgentRunner],
    threshold: float = ev.DEFAULT_THRESHOLD,
    artifact: Optional[Path] = None,
    evals_dir: Optional[Path] = None,
    max_workers: int = 3,
    ts: str = "",
) -> EvalRunResult:
    """End-to-end eval. PROMPT mode runs each input through `make_sut`; ARTIFACT
    mode grades `artifact`'s text for every case. Grading always uses a DISTINCT
    `make_grader` agent (maker≠grader, enforced per case in PROMPT mode).
    """
    path = eval_set_path(root, name)
    if not path.exists():
        return EvalRunResult(ok=False, set_name=name, error=f"no eval set at {path}")
    try:
        cases = ev.parse_eval_set(path.read_text())
    except OSError as exc:
        return EvalRunResult(ok=False, set_name=name, error=f"could not read eval set: {exc}")
    if not cases:
        return EvalRunResult(ok=True, set_name=name, skipped_reason="eval set has no cases")

    # ARTIFACT mode: read the artifact once, grade every case against it.
    artifact_text: Optional[str] = None
    if artifact is not None:
        if not artifact.exists():
            return EvalRunResult(ok=False, set_name=name, error=f"artifact not found: {artifact}")
        try:
            artifact_text = artifact.read_text()
        except OSError as exc:
            return EvalRunResult(ok=False, set_name=name, error=f"could not read artifact: {exc}")

    # Cost estimate (advisory): one SUT + one grade per case (≈2 units in prompt
    # mode, 1 in artifact mode).
    units = len(cases) * (1 if artifact_text is not None else 2)
    rows = read_ledger(ledger_path(root))
    est = estimate("eval", units=units, rows=rows)

    def produce_and_grade(case: ev.EvalCase) -> Tuple[str, bool, str]:
        if artifact_text is not None:
            return _grade_case(case, artifact_text, make_grader, sut=None, cwd=root)
        sut = make_sut()
        out = sut.run(case.input, cwd=root, role="eval-sut")
        actual = out.output if out.ok else f"(system-under-test failed: {out.error})"
        return _grade_case(case, actual, make_grader, sut=sut, cwd=root)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(produce_and_grade, cases))
    except ValueError as exc:
        # ensure_distinct misconfiguration → clean failure, never a traceback.
        return EvalRunResult(ok=False, set_name=name, error=str(exc))

    report = ev.aggregate(results)
    decision = ev.gate(report, threshold=threshold)
    text = ev.render_report(report, decision, set_name=name)

    out_dir = evals_dir or (root / "sigma" / "evals")
    report_path: Optional[Path] = None
    write_error: Optional[str] = None
    try:
        report_path = _write_report(out_dir, name, text)
    except OSError as exc:
        write_error = f"could not write report: {exc}"

    _record_cost(root, est, len(results), ts)

    return EvalRunResult(
        ok=True, gate=decision, report=text, report_path=report_path,
        set_name=name, error=write_error,
    )


def _write_report(evals_dir: Path, name: str, report: str) -> Path:
    out = evals_dir / name / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    return out


def _record_cost(root: Path, est, ran_units: int, ts: str) -> None:
    """Append a cost row (best-effort; never raises into the eval flow)."""
    if not ts:
        return
    try:
        row = build_record(
            "eval", units=est.units, tokens=est.estimated_tokens,
            ts=ts, estimated=est.estimated_tokens, models=est.routing,
        )
        append_ledger(ledger_path(root), row)
    except OSError:
        pass
