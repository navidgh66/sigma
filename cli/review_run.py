"""`sigma review` — three-axis review of a change set (local diff or PR).

Wires the pure review logic (`cli/review.py`) to real subprocesses:

  - resolve the change set: `git diff` (local) or `gh pr diff` (PR);
  - load the logic profile + recalled lessons + a staleness banner;
  - fan the three axes (code / ml-logic / system-logic) out in PARALLEL through
    distinct AgentRunner instances (true concurrency a single session can't do —
    the CLI-only capability, like `research`);
  - aggregate findings, decide the gate (fail on CRITICAL/HIGH or inconclusive),
    write the markdown report, post a PR summary in PR mode, and ratchet blocking
    findings into `skills/` so the next review recalls them.

The git/gh/agent calls are injectable so the whole flow is testable with fakes.
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from cli import review as rv
from cli.cost import build_record, estimate, ledger_path, read_ledger
from cli.domains_index import context_engines_dir
from cli.loop import ratchet_to_skills
from cli.profile_manifest import profile_path, staleness
from cli.runner import AgentRunner
from cli.skills_recall import recall_lessons, render_recall_block


@dataclass
class ReviewResult:
    ok: bool
    gate: Optional[rv.Gate] = None
    report: str = ""
    report_path: Optional[Path] = None
    pr_comment: str = ""
    ratcheted: List[Path] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    error: Optional[str] = None
    skipped_reason: Optional[str] = None


# --------------------------------------------------------------------------- #
# Change-set resolution (injectable subprocess)
# --------------------------------------------------------------------------- #
def _run(argv: List[str], cwd: Optional[Path], runner: Callable) -> str:
    """Run a command, return stdout ('' on any failure — resolution is best-effort)."""
    try:
        proc = runner(argv, capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    except (FileNotFoundError, OSError):
        return ""
    if getattr(proc, "returncode", 1) != 0:
        return ""
    return (getattr(proc, "stdout", "") or "")


def resolve_change_set(
    target: Optional[str],
    root: Path,
    runner: Callable = subprocess.run,
) -> rv.ChangeSet:
    """Resolve the change set to review.

    `target` empty/None → local diff (working tree + staged vs HEAD); a value that
    looks like a range (`a..b`) → that git range; otherwise treat it as a PR
    number/URL and use `gh pr diff`. Falls back to an empty change set on failure
    (which the caller treats as "nothing to review", not an error).
    """
    if target and ".." in target:
        diff = _run(["git", "diff", target], root, runner)
        return rv.build_change_set(diff, source="local", ref=target)
    if target:
        diff = _run(["gh", "pr", "diff", target], root, runner)
        return rv.build_change_set(diff, source="pr", ref=target)
    # Local uncommitted + staged changes vs HEAD.
    diff = _run(["git", "diff", "HEAD"], root, runner)
    return rv.build_change_set(diff, source="local", ref=None)


def _load_logic_evaluator(domains: List[str], home: Optional[Path] = None) -> str:
    """Concatenate the logic-evaluator.md for the inferred domains (ml-logic axis)."""
    blocks: List[str] = []
    base = context_engines_dir(home)
    for d in domains:
        f = base / d / "verifiers" / "logic-evaluator.md"
        if f.exists():
            try:
                blocks.append(f.read_text())
            except OSError:
                continue
    return "\n\n".join(blocks)


def _post_pr_comment(ref: str, body: str, root: Path, runner: Callable) -> bool:
    """Post a PR summary comment via `gh`. No-op-safe: returns False on any failure."""
    try:
        proc = runner(
            ["gh", "pr", "comment", ref, "--body", body],
            capture_output=True, text=True, cwd=str(root),
        )
    except (FileNotFoundError, OSError):
        return False
    return getattr(proc, "returncode", 1) == 0


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_review(
    target: Optional[str],
    root: Path,
    skills_dir: Path,
    make_runner: Callable[[], AgentRunner],
    reviews_dir: Optional[Path] = None,
    cmd_runner: Callable = subprocess.run,
    home: Optional[Path] = None,
    ts: str = "",
    max_workers: int = 3,
) -> ReviewResult:
    """End-to-end review. `make_runner` yields a FRESH AgentRunner per axis.

    The three runners are asserted distinct (maker≠checker analog). Empty diff →
    a clean skip. Blocking findings ratchet into `skills/`. A cost estimate is
    computed up front and the actual unit count recorded after.
    """
    change = resolve_change_set(target, root, runner=cmd_runner)
    if change.is_empty:
        return ReviewResult(ok=True, skipped_reason="nothing to review (empty diff)")

    domains = rv.infer_domains(change.files)

    # Grounding: profile text + staleness banner + recalled lessons (per domain).
    prof = profile_path(root)
    profile_text = ""
    if prof.exists():
        try:
            profile_text = prof.read_text()
        except OSError:
            profile_text = ""
    touched = [root / f for f in change.files]
    banner = staleness(prof, touched).banner()
    recall_block = _recall_for(skills_dir, domains)
    logic_eval = _load_logic_evaluator(domains, home=home)

    # Cost estimate (advisory): units = axes × files.
    rows = read_ledger(ledger_path(root))
    est = estimate("review", units=len(rv.AXES) * len(change.files), rows=rows)

    # Build distinct runners and fan out the three axes in parallel.
    runners = {axis: make_runner() for axis in rv.AXES}
    try:
        rv.ensure_distinct_axes(list(runners.values()))
    except ValueError as exc:
        # Misconfigured caller (same runner reused) — surface as a clean failure,
        # never a traceback out of run_review.
        return ReviewResult(ok=False, error=str(exc))
    prompts = {
        axis: rv.build_axis_prompt(
            axis, change,
            profile_text=profile_text,
            recall_block=recall_block,
            staleness_banner=banner,
            logic_evaluator_text=logic_eval if axis == "ml-logic" else "",
        )
        for axis in rv.AXES
    }

    results = _fan_out(runners, prompts, root, max_workers)
    decision = rv.gate(results)
    report = rv.render_report(change, results, decision, domains)

    # Writing the report / ratcheting touch disk — degrade gracefully on OSError
    # (read-only fs, disk full) rather than crashing a completed review.
    out_dir = reviews_dir or (root / "sigma" / "reviews")
    report_path: Optional[Path] = None
    write_error: Optional[str] = None
    try:
        report_path = _write_report(out_dir, change, report)
    except OSError as exc:
        write_error = f"could not write report: {exc}"

    # PR mode: post a summary comment (no-op-safe).
    pr_comment = ""
    if change.source == "pr" and change.ref:
        pr_comment = rv.render_pr_comment(change, decision)
        _post_pr_comment(change.ref, pr_comment, root, cmd_runner)

    # Ratchet blocking findings so the next review recalls them.
    try:
        ratcheted = _ratchet_blocking(skills_dir, decision, domains)
    except OSError as exc:
        ratcheted = []
        write_error = (write_error + "; " if write_error else "") + f"could not ratchet: {exc}"

    # Record actual cost units (tokens unknown here → store the estimate as both;
    # a richer integration can pass true token counts later).
    _record_cost(root, est, ts)

    return ReviewResult(
        ok=True, gate=decision, report=report, report_path=report_path,
        pr_comment=pr_comment, ratcheted=ratcheted, domains=domains, error=write_error,
    )


def _recall_for(skills_dir: Path, domains: List[str]) -> str:
    """Build one recall block across the inferred domains (deduped, capped)."""
    blocks: List[str] = []
    for d in domains:
        block = render_recall_block(recall_lessons(skills_dir, d))
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _fan_out(
    runners: Dict[str, AgentRunner],
    prompts: Dict[str, str],
    cwd: Path,
    max_workers: int,
) -> List[rv.AxisResult]:
    """Run the axes concurrently; parse each into an AxisResult (order = AXES).

    Any exception in an axis (a broken runner, a parse error) degrades that axis to
    inconclusive rather than crashing the fan-out — the gate then treats it as a
    non-pass (skeptical), never a silent success.
    """
    def one(axis: str) -> rv.AxisResult:
        try:
            res = runners[axis].run(prompts[axis], cwd=cwd)
            if not res.ok:
                return rv.AxisResult(axis=axis, ran=False, error=res.error or "agent failed")
            return rv.AxisResult(
                axis=axis, ran=True, findings=rv.parse_findings(axis, res.output)
            )
        except Exception as exc:  # noqa: BLE001 — any axis failure → inconclusive, not a crash
            return rv.AxisResult(axis=axis, ran=False, error=str(exc))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {axis: pool.submit(one, axis) for axis in rv.AXES}
        return [futures[axis].result() for axis in rv.AXES]


def _write_report(reviews_dir: Path, change: rv.ChangeSet, report: str) -> Path:
    """Write the markdown report under sigma/reviews/<slug>/review.md."""
    from cli.paths import slugify

    slug = slugify(change.ref or change.source or "review")
    out = reviews_dir / slug / "review.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    return out


def _ratchet_blocking(
    skills_dir: Path, decision: rv.Gate, domains: List[str]
) -> List[Path]:
    """Ratchet each CRITICAL/HIGH finding into skills/ (recalled next review).

    Each finding is tagged with the domain inferred from ITS OWN file, so it is
    recalled in the right domain's future reviews — not blanket-tagged with the
    first inferred domain. Falls back to the change-wide first domain when the
    finding has no file (or its file matches no hint).
    """
    fallback = domains[0] if domains else None
    paths: List[Path] = []
    for f in decision.blocking:
        domain = fallback
        if f.file:
            inferred = rv.infer_domains([f.file])
            # infer_domains is never empty (defaults to classic-ml); prefer it
            # only when the file actually matched a hint, else keep the fallback.
            if inferred and inferred != [rv.DEFAULT_DOMAIN]:
                domain = inferred[0]
        title = f"review finding: {f.message.strip()[:80]}"
        lesson = f"[{f.severity}/{f.axis}] {f.file or '-'}: {f.message.strip()}"
        paths.append(ratchet_to_skills(skills_dir, title, lesson, domain))
    return paths


def _record_cost(root: Path, est, ts: str) -> None:
    """Append a cost row (best-effort; never raises into the review flow)."""
    if not ts:
        return
    try:
        from cli.cost import append_ledger

        row = build_record(
            "review", units=est.units, tokens=est.estimated_tokens,
            ts=ts, estimated=est.estimated_tokens, models=est.routing,
        )
        append_ledger(ledger_path(root), row)
    except OSError:
        pass
