"""Loop engine: parse tasks, drive maker/checker cycles, ratchet failures.

Pure logic lives here (task parsing, cycle planning, ratchet rendering) so it is
fully testable without spawning real agents or worktrees. The CLI layer wires
this to real subprocesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from cli.runner import AgentRunner, write_artifact

# A task line in tasks.md, e.g.:
#   - [ ] T1 (nlp): tokenize corpus
#   - [x] T2 (mlops): register model
TASK_RE = re.compile(
    r"^\s*-\s*\[(?P<done>[ xX])\]\s*"
    r"(?P<id>[A-Za-z]+\d+)?\s*"
    r"(?:\((?P<domain>[a-z-]+)\))?\s*:?\s*"
    r"(?P<title>.+?)\s*$"
)


@dataclass
class Task:
    raw: str
    title: str
    done: bool
    id: Optional[str] = None
    domain: Optional[str] = None


@dataclass
class CyclePlan:
    task: Task
    worktree_name: str
    implementer_domain: str
    verifier_domain: str

    def valid_maker_checker(self) -> bool:
        """Maker and checker must be distinct agents (same domain, separate runs)."""
        # Separation is by agent role, not domain; we assert both roles are set.
        return bool(self.implementer_domain) and bool(self.verifier_domain)


def parse_tasks(markdown: str) -> List[Task]:
    """Parse a tasks.md body into Task objects."""
    tasks: List[Task] = []
    for line in markdown.splitlines():
        if "- [" not in line:
            continue
        m = TASK_RE.match(line)
        if not m:
            continue
        tasks.append(
            Task(
                raw=line.rstrip(),
                title=m.group("title").strip(),
                done=m.group("done").lower() == "x",
                id=m.group("id"),
                domain=m.group("domain"),
            )
        )
    return tasks


def incomplete_tasks(tasks: List[Task]) -> List[Task]:
    return [t for t in tasks if not t.done]


def plan_cycle(task: Task) -> CyclePlan:
    """Build a maker/checker cycle plan for a task."""
    domain = task.domain or "ai-agent-engineering"
    name = (task.id or task.title[:20]).lower().replace(" ", "-")
    return CyclePlan(
        task=task,
        worktree_name=f"sigma-loop-{name}",
        implementer_domain=domain,
        verifier_domain=domain,
    )


def select_next(tasks: List[Task], max_cycles: int, completed_count: int) -> Optional[CyclePlan]:
    """Pick the next task to work on, respecting the budget cap."""
    if completed_count >= max_cycles:
        return None
    pending = incomplete_tasks(tasks)
    if not pending:
        return None
    return plan_cycle(pending[0])


def render_skill(failure_title: str, lesson: str, domain: Optional[str] = None) -> str:
    """Render a SKILL.md body that ratchets a failure into permanent knowledge."""
    slug = re.sub(r"[^a-z0-9]+", "-", failure_title.lower()).strip("-") or "lesson"
    front = ["---", f"name: {slug}", f"description: Avoid recurrence of: {failure_title}"]
    if domain:
        front.append(f"metadata:\n  domain: {domain}")
    front.append("---")
    body = [
        "",
        f"# {failure_title}",
        "",
        "**What failed:** " + failure_title,
        "",
        "**Lesson (ratcheted):** " + lesson,
        "",
        "**How to apply:** Check this before implementing similar work in "
        f"the `{domain or 'relevant'}` domain.",
        "",
    ]
    return "\n".join(front + body)


def ratchet_to_skills(skills_dir: Path, failure_title: str, lesson: str, domain: Optional[str] = None) -> Path:
    """Write a ratcheted lesson into skills/ so the loop never repeats it.

    Before writing, check for an existing lesson on the same domain + topic. If
    found, flag a contradiction (in the new skill + a central CONTRADICTIONS.md)
    for human review — never auto-resolve or delete the existing lesson.
    """
    from cli.skills_index import find_contradictions, topic_key

    slug = re.sub(r"[^a-z0-9]+", "-", failure_title.lower()).strip("-") or "lesson"
    target = skills_dir / slug
    target.mkdir(parents=True, exist_ok=True)
    out = target / "SKILL.md"

    conflicts = find_contradictions(skills_dir, domain, topic_key(failure_title))
    body = render_skill(failure_title, lesson, domain)
    if conflicts:
        marker = (
            "\n> ⚠ CONTRADICTION: this lesson may conflict with "
            + ", ".join(str(p.relative_to(skills_dir)) for p in conflicts)
            + " — human review needed.\n"
        )
        body = body + marker
        flag_contradiction(skills_dir, out, conflicts, domain)
    out.write_text(body)
    return out


def flag_contradiction(
    skills_dir: Path, new_skill: Path, conflicts: List[Path], domain: Optional[str]
) -> Path:
    """Append a flag to skills/CONTRADICTIONS.md. Never resolves — humans decide."""
    flag = skills_dir / "CONTRADICTIONS.md"
    if not flag.exists():
        flag.write_text("# Contradictions (human review)\n\n")
    existing = ", ".join(str(p.relative_to(skills_dir)) for p in conflicts)
    with flag.open("a") as fh:
        fh.write(f"- [{domain or '-'}] {new_skill.relative_to(skills_dir)} vs {existing}\n")
    return flag


def append_loop_log(workspace: Path, message: str) -> Path:
    """Append a line to the loop log (persistent external state)."""
    workspace.mkdir(parents=True, exist_ok=True)
    log = workspace / "loop-log.md"
    if not log.exists():
        log.write_text("# Loop log\n\n")
    with log.open("a") as fh:
        fh.write(f"- {message}\n")
    return log


def record_cycle_steps(outcomes: List["CycleOutcome"], sink) -> None:
    """Emit one role="cycle" trajectory step per outcome (ok = outcome.verified).

    This is the real, measured pass/fail signal `trajectory.efficiency_report`
    reads for cycle pass rate — distinct from a subprocess crash (`ok` on an
    implementer/verifier step means "exited zero", not "verdict passed"). `sink`
    is the same best-effort callable `AgentRunner` uses; a broken sink degrades
    silently (observability must never break a run).
    """
    for outcome in outcomes:
        sink({"role": "cycle", "ok": outcome.verified})


# --------------------------------------------------------------------------- #
# Cycle execution (maker → checker → ratchet)
# --------------------------------------------------------------------------- #
IMPLEMENT_PROMPT = (
    "Implement this sigma task in domain '{domain}':\n{title}\n\n"
    "Follow the domain implementer guidance. Make the smallest correct change."
)
VERIFY_PROMPT = (
    "Independently verify the implementation of this task (you are the CHECKER, "
    "a different agent from the implementer — do not assume it is correct):\n"
    "Domain: {domain}\nTask: {title}\n\n"
    "Apply the domain verifier checks. Reply with a final line exactly:\n"
    "VERDICT: PASS  or  VERDICT: FAIL"
)
LOGIC_PROMPT = (
    "You are the LOGIC EVALUATOR — a third agent, distinct from both the "
    "implementer and the code-quality checker. Do NOT grade style or lint. "
    "Grade whether the reasoning is sound and the implementation matches the "
    "plan/spec, per the domain logic-evaluator guidance.\n"
    "Domain: {domain}\nTask: {title}\n\n"
    "Check: plan↔implementation coherence, logical soundness, hidden "
    "assumptions, ignored edge cases, reasoning gaps. Reply with a final line "
    "exactly:\nVERDICT: PASS  or  VERDICT: FAIL"
)
# TDD axis: a distinct TEST WRITER pens a failing test (RED) BEFORE the
# implementer exists. The implementer then sees this test and must make it pass
# (GREEN) without weakening its intent — one agent codes, another tests.
TEST_PROMPT = (
    "You are the TEST WRITER — a distinct agent from the implementer, the "
    "code-quality checker, and the logic evaluator. Write a FAILING test (RED) "
    "that pins the acceptance criteria for this task BEFORE any implementation "
    "exists. Do NOT implement the feature. The test must fail because the feature "
    "is absent — not because of a syntax error.\n"
    "Domain: {domain}\nTask: {title}\n\n"
    "Output the test code and one line naming the behavior it pins."
)
# Prepended to the implementer prompt in TDD mode so the maker codes against the
# already-written failing test.
TDD_IMPLEMENT_PREFIX = (
    "A failing test was written FIRST (TDD). Make it pass without weakening what "
    "it checks — do not edit the test to fit the code:\n{test}\n\n"
)
# On a verify failure in TDD mode, the test writer pens a REGRESSION test that
# pins the bug the checker just found, so the loop can never silently regress on
# it again. The maker never edits this test (maker ≠ tester is already enforced).
REGRESSION_PROMPT = (
    "You are the TEST WRITER. The implementation of this task FAILED verification. "
    "Write a REGRESSION test that pins the specific bug the checker found, so it can "
    "never silently recur. Do NOT fix the code — only encode the missing guarantee.\n"
    "Domain: {domain}\nTask: {title}\n"
    "Checker's failure reason: {reason}\n\n"
    "Output the regression test code and one line naming the bug it guards against."
)
# Anti-slop axis: a DISTINCT simplifier agent runs AFTER a cycle PASSES (cleanup,
# not a gate). It only changes HOW the code reads, never WHAT it does — the
# behaviour-preservation guard is a re-verify (a regression reverts the simplify,
# never the feature). Four axes mirror Anthropic's bundled /simplify: reuse,
# simplification, efficiency, right-altitude.
SIMPLIFY_PROMPT = (
    "You are the SIMPLIFIER — a distinct agent from the implementer, checker, "
    "logic evaluator, and test writer. The implementation already PASSED "
    "verification. Refine it to fight AI slop while PRESERVING BEHAVIOUR EXACTLY "
    "— change only HOW the code reads, never WHAT it does. Touch only code this "
    "task changed.\n"
    "Domain: {domain}\nTask: {title}\n\n"
    "Apply four axes:\n"
    "1. Reuse — does it duplicate logic that an existing helper/util already "
    "provides? Call the existing one.\n"
    "2. Simplify — remove dead code, unused params/imports, needless wrappers and "
    "single-use abstractions, deep nesting (use early returns), nested ternaries, "
    "clever one-liners. Clarity over brevity.\n"
    "3. Efficiency — only behaviour-preserving wins (hoist repeated work, obvious "
    "O(n^2)->O(n)).\n"
    "4. Right altitude — neither premature generality (YAGNI) nor copy-paste that "
    "should be one helper.\n\n"
    "Do NOT over-simplify: keep abstractions that genuinely reduce duplication; "
    "never trade readability for fewer lines. If a change's behavioural safety is "
    "uncertain, DO NOT make it — leave the code and note it.\n"
    "Output the refined code (or 'NO CHANGES NEEDED' if already clean)."
)

# Escalation axis: on a verify/logic FAIL (not every turn — see the "verifier-critic
# + uncertainty escalation" pattern, distinct from per-turn self-reflection), a
# DISTINCT, stronger-tier advisor reviews the failure and drafts a correction plan.
# The implementer retries with that plan prefixed; the cycle re-verifies. Bounded by
# advisor_rounds with a no-progress stop. Mirrors _run_simplify's distinctness law
# but on the opposite branch — this axis fires on FAIL, simplify fires on PASS.
ADVISOR_PROMPT = (
    "You are the ADVISOR — a distinct agent from the implementer, checker, logic "
    "evaluator, test writer, and simplifier. The implementation of this task FAILED "
    "verification. Do NOT rewrite the code yourself. Review the implementation and "
    "the checker's failure reason, then produce a concrete, minimal CORRECTION PLAN "
    "the implementer can follow to fix the root cause.\n"
    "Domain: {domain}\nTask: {title}\n"
    "Implementation output:\n{impl}\n\nChecker's failure reason: {reason}\n\n"
    "Output the correction plan as numbered steps, and one line naming the root cause."
)
ADVISOR_RETRY_PREFIX = (
    "A prior attempt FAILED verification. An advisor reviewed it and produced this "
    "correction plan — follow it to fix the root cause without regressing what "
    "already worked:\n{plan}\n\n"
)


@dataclass
class CycleOutcome:
    task_title: str
    implemented: bool
    verified: bool
    logic_ok: Optional[bool] = None
    test_written: Optional[bool] = None  # set only in TDD mode
    regression_test: Optional[Path] = None  # TDD: test pinning a verify-fail bug
    simplified: Optional[bool] = None  # set only in --simplify mode: did cleanup stick?
    advised: Optional[bool] = None  # set only in --advisor mode: did escalation rescue the cycle?
    advisor_rounds_used: Optional[int] = None  # set only in --advisor mode
    ratcheted_skill: Optional[Path] = None
    contradiction: Optional[Path] = None
    notes: List[str] = field(default_factory=list)


def _verdict_pass(verify_output: str) -> bool:
    """Parse the checker's verdict line. Defaults to FAIL if absent (skeptical)."""
    for line in reversed(verify_output.splitlines()):
        line = line.strip().upper()
        if line.startswith("VERDICT:"):
            return "PASS" in line
    return False


def _run_verify(
    plan: CyclePlan,
    workspace: Path,
    verifier: AgentRunner,
    logic_checker: Optional[AgentRunner],
    recall: str,
) -> tuple:
    """Run the verify (+ optional logic) axis once. Returns (passed, logic_ok, reason, detail).

    `logic_ok` is None when no logic_checker was given (mirrors `CycleOutcome.logic_ok`'s
    default). `reason`/`detail` are only meaningful when `passed` is False: `reason` is
    the short, stable message used for ratchet/log text (unchanged across identical
    failure *kinds*, e.g. "verifier returned VERDICT: FAIL"); `detail` is the raw
    checker/logic output text, used by the advisor's no-progress check so two FAILs of
    the same kind but with genuinely different content aren't mistaken for no-progress.
    Writes the same verify/logic artifacts execute_cycle always wrote — callers may
    invoke this more than once (advisor retries), each call overwriting the prior
    attempt's artifacts, so only the LAST attempt's verify output persists on disk (the
    outcome/ratchet bookkeeping still reflects every round via the caller).
    """
    title = plan.task.title
    domain = plan.implementer_domain
    chk = verifier.run(
        _with_recall(VERIFY_PROMPT.format(domain=domain, title=title), recall),
        cwd=workspace,
        role="verifier",
    )
    write_artifact(workspace / "verify" / f"{plan.worktree_name}.md", chk.output)
    quality_passed = chk.ok and _verdict_pass(chk.output)

    logic_ok: Optional[bool] = None
    logic_passed = True
    logic_output = ""
    if logic_checker is not None:
        logic = logic_checker.run(
            LOGIC_PROMPT.format(domain=domain, title=title), cwd=workspace, role="logic"
        )
        write_artifact(workspace / "verify" / f"{plan.worktree_name}.logic.md", logic.output)
        logic_passed = logic.ok and _verdict_pass(logic.output)
        logic_ok = logic_passed
        logic_output = logic.output

    passed = quality_passed and logic_passed
    if passed:
        return True, logic_ok, "", ""
    if not quality_passed:
        reason = chk.error if not chk.ok else "verifier returned VERDICT: FAIL"
    else:
        reason = "logic evaluator returned VERDICT: FAIL"
    detail = f"{chk.output}\n{logic_output}".strip()
    return False, logic_ok, reason, detail


def _run_advisor_escalation(
    plan: CyclePlan,
    workspace: Path,
    implementer: AgentRunner,
    verifier: AgentRunner,
    logic_checker: Optional[AgentRunner],
    advisor: AgentRunner,
    advisor_rounds: int,
    reason: str,
    detail: str,
    recall: str,
    impl_output: str,
    outcome: CycleOutcome,
) -> tuple:
    """Escalate a verify/logic FAIL to a distinct advisor before ratcheting.

    Bounded by `advisor_rounds`: each round, the advisor drafts a correction plan
    from the current failure reason, the implementer retries with that plan
    prefixed, and the cycle re-verifies. Stops early (no-progress) when a round's
    raw checker/logic output (`detail`) is identical to the previous round's — the
    advisor isn't helping (comparing `reason`, the short stable label, would false-
    trigger on any two FAILs of the same kind even with genuinely different
    content). On rescue, returns (True, ""). On exhaustion, REVERTS the workspace's
    impl/verify artifacts to the pre-escalation implementation (the last retry's
    edits may be worse than the original failing code — there is no guarantee an
    unfinished correction is an improvement) and returns (False, <last reason>).
    An advisor crash stops escalation immediately (best-effort, never fatal).
    """
    title = plan.task.title
    domain = plan.implementer_domain
    original_impl_output = impl_output
    rounds_used = 0

    for round_i in range(1, advisor_rounds + 1):
        rounds_used = round_i
        plan_result = advisor.run(
            ADVISOR_PROMPT.format(domain=domain, title=title, impl=impl_output, reason=reason),
            cwd=workspace,
            role="advisor",
        )
        if not plan_result.ok:
            outcome.notes.append(f"advisor skipped: {plan_result.error}")
            break
        write_artifact(
            workspace / "advisor" / f"{plan.worktree_name}.round{round_i}.md", plan_result.output
        )

        retry_prompt = ADVISOR_RETRY_PREFIX.format(plan=plan_result.output) + IMPLEMENT_PROMPT.format(
            domain=domain, title=title
        )
        impl = implementer.run(_with_recall(retry_prompt, recall), cwd=workspace, role="implementer")
        if not impl.ok:
            outcome.notes.append(f"advisor retry implement failed: {impl.error}")
            break
        impl_output = impl.output
        write_artifact(workspace / "impl" / f"{plan.worktree_name}.md", impl_output)

        passed, logic_ok, new_reason, new_detail = _run_verify(
            plan, workspace, verifier, logic_checker, recall
        )
        if logic_ok is not None:
            outcome.logic_ok = logic_ok
        if passed:
            outcome.advised = True
            outcome.advisor_rounds_used = rounds_used
            append_loop_log(workspace, f"{title}: advisor rescued cycle (round {round_i})")
            return True, ""
        if new_detail == detail:
            outcome.notes.append(f"advisor no-progress stop (round {round_i})")
            append_loop_log(workspace, f"{title}: advisor no-progress stop (round {round_i})")
            reason = new_reason
            break
        reason, detail = new_reason, new_detail

    outcome.advised = False
    outcome.advisor_rounds_used = rounds_used
    # Exhausted (or crashed/aborted): revert to the pre-escalation implementation so
    # a failed correction attempt never leaves the workspace worse than it started.
    write_artifact(workspace / "impl" / f"{plan.worktree_name}.md", original_impl_output)
    append_loop_log(workspace, f"{title}: advisor exhausted ({rounds_used} round(s)) — reverted")
    return False, reason


def _with_recall(prompt: str, recall: str) -> str:
    """Prepend the past-lessons recall block to a prompt (no-op when empty).

    Empty recall leaves the prompt byte-identical to the no-lessons case, so
    recall is a strict, fail-safe addition.
    """
    if not recall:
        return prompt
    return f"{recall}\n\n{prompt}"


def execute_cycle(
    plan: CyclePlan,
    workspace: Path,
    skills_dir: Path,
    implementer: AgentRunner,
    verifier: AgentRunner,
    logic_checker: Optional[AgentRunner] = None,
    recall: str = "",
    test_writer: Optional[AgentRunner] = None,
    simplifier: Optional[AgentRunner] = None,
    advisor: Optional[AgentRunner] = None,
    advisor_rounds: int = 1,
) -> CycleOutcome:
    """Run one maker→checker cycle. On failure, ratchet a lesson into skills/.

    `implementer` and `verifier` MUST be distinct runner instances (maker ≠
    checker). They are injectable, so this is testable with fakes.

    When `logic_checker` is provided it runs a SECOND, independent verify axis:
    the logic evaluator grades reasoning + plan-coherence (not code quality). It
    must be distinct from both implementer and verifier. The cycle passes only
    when BOTH the code-quality verifier and the logic evaluator pass.

    When `test_writer` is provided (TDD mode), a distinct agent writes a FAILING
    test BEFORE the implementer runs; the implementer's prompt is then prefixed
    with that test and told to make it pass without weakening it (one agent codes,
    another tests). The test writer must be distinct from all other agents.

    When `advisor` is provided, a verify/logic FAIL escalates to a distinct advisor
    (see `_run_advisor_escalation`) before falling through to the ratchet path.
    `advisor` is None by default, so the escalation branch never runs unless the
    caller opts in — the rest of the function is byte-identical to before this axis
    existed.

    `recall` is an optional past-lessons block (from cli.skills_recall) prepended
    to the implement + verify prompts so the maker avoids prior mistakes and the
    checker checks against them. It is NOT added to the logic prompt (that grades
    reasoning, not domain patterns). Empty `recall` → prompts unchanged.
    """
    if implementer is verifier:
        raise ValueError("maker and checker must be distinct agents")
    if logic_checker is not None and (
        logic_checker is implementer or logic_checker is verifier
    ):
        raise ValueError("logic checker must be distinct from maker and checker")
    if test_writer is not None and (
        test_writer is implementer
        or test_writer is verifier
        or test_writer is logic_checker
    ):
        raise ValueError("test writer must be distinct from maker, checker, and logic agents")
    if simplifier is not None and (
        simplifier is implementer
        or simplifier is verifier
        or simplifier is logic_checker
        or simplifier is test_writer
    ):
        raise ValueError(
            "simplifier must be distinct from maker, checker, logic, and test agents"
        )
    if advisor is not None and (
        advisor is implementer
        or advisor is verifier
        or advisor is logic_checker
        or advisor is test_writer
        or advisor is simplifier
    ):
        raise ValueError(
            "advisor must be distinct from maker, checker, logic, test, and simplifier agents"
        )

    title = plan.task.title
    domain = plan.implementer_domain
    outcome = CycleOutcome(task_title=title, implemented=False, verified=False)

    # TDD: a distinct agent writes the failing test FIRST. Its output is fed to the
    # implementer. A failed test-writing step aborts the cycle (nothing to build
    # against) and ratchets the failure.
    implement_prompt = IMPLEMENT_PROMPT.format(domain=domain, title=title)
    if test_writer is not None:
        test = test_writer.run(
            TEST_PROMPT.format(domain=domain, title=title), cwd=workspace, role="test-writer"
        )
        outcome.test_written = test.ok
        if not test.ok:
            outcome.notes.append(f"test-writing failed: {test.error}")
            outcome.ratcheted_skill = ratchet_to_skills(
                skills_dir, f"test-writing failed: {title}", test.error or "unknown", domain
            )
            outcome.contradiction = _contradiction_flag(skills_dir, outcome.ratcheted_skill)
            append_loop_log(workspace, f"{title}: test-writing FAILED ({test.error})")
            return outcome
        write_artifact(workspace / "tests" / f"{plan.worktree_name}.md", test.output)
        implement_prompt = TDD_IMPLEMENT_PREFIX.format(test=test.output) + implement_prompt

    impl = implementer.run(
        _with_recall(implement_prompt, recall),
        cwd=workspace,
        role="implementer",
    )
    outcome.implemented = impl.ok
    if not impl.ok:
        outcome.notes.append(f"implement failed: {impl.error}")
        outcome.ratcheted_skill = ratchet_to_skills(
            skills_dir, f"implement failed: {title}", impl.error or "unknown", domain
        )
        outcome.contradiction = _contradiction_flag(skills_dir, outcome.ratcheted_skill)
        append_loop_log(workspace, f"{title}: implement FAILED ({impl.error})")
        return outcome

    write_artifact(workspace / "impl" / f"{plan.worktree_name}.md", impl.output)

    passed, logic_ok, reason, detail = _run_verify(plan, workspace, verifier, logic_checker, recall)
    if logic_ok is not None:
        outcome.logic_ok = logic_ok
    outcome.verified = passed

    # Escalation: on a FAIL, a distinct advisor may rescue the cycle before it
    # falls through to the ratchet path. Runs BEFORE the pass/fail branch below so
    # a rescue is indistinguishable, downstream, from a first-try pass.
    if not passed and advisor is not None:
        passed, reason = _run_advisor_escalation(
            plan, workspace, implementer, verifier, logic_checker,
            advisor, advisor_rounds, reason, detail, recall, impl.output, outcome,
        )
        outcome.verified = passed

    if passed:
        append_loop_log(workspace, f"{title}: PASS")
        # Anti-slop cleanup runs ONLY after a pass (it polishes verified code, it
        # is not a gate). A distinct simplifier refines for clarity; the verifier
        # then re-checks to confirm behaviour was preserved — a regression reverts
        # the simplify, never the feature. Best-effort: a failed simplify is logged
        # and the (already-passing) cycle stands.
        if simplifier is not None:
            _run_simplify(plan, workspace, simplifier, verifier, outcome)
    else:
        outcome.notes.append(f"verify failed: {reason}")
        outcome.ratcheted_skill = ratchet_to_skills(
            skills_dir, f"verify failed: {title}", reason, domain
        )
        outcome.contradiction = _contradiction_flag(skills_dir, outcome.ratcheted_skill)
        append_loop_log(workspace, f"{title}: verify FAILED ({reason})")
        # TDD: pin the bug with a regression test so the loop can never silently
        # regress on it. Best-effort — a failed write is logged, never fatal.
        if test_writer is not None:
            reg = test_writer.run(
                REGRESSION_PROMPT.format(domain=domain, title=title, reason=reason),
                cwd=workspace,
                role="test-writer",
            )
            if reg.ok:
                outcome.regression_test = write_artifact(
                    workspace / "regressions" / f"{plan.worktree_name}.md", reg.output
                )
                append_loop_log(workspace, f"{title}: regression test pinned")
            else:
                outcome.notes.append(f"regression-test write failed: {reg.error}")
    return outcome


def _run_simplify(
    plan: CyclePlan,
    workspace: Path,
    simplifier: AgentRunner,
    verifier: AgentRunner,
    outcome: CycleOutcome,
) -> None:
    """Run the post-pass anti-slop cleanup with a behaviour-preservation guard.

    The simplifier refines the already-verified implementation; the SAME verifier
    re-checks the result. `outcome.simplified` is True only when the cleanup ran
    AND survived re-verification (behaviour preserved). A simplifier crash, or a
    re-verify FAIL, leaves the passing cycle untouched and records the reason —
    cleanup never turns a green cycle red.
    """
    title = plan.task.title
    domain = plan.implementer_domain
    simp = simplifier.run(
        SIMPLIFY_PROMPT.format(domain=domain, title=title),
        cwd=workspace,
        role="simplifier",
    )
    if not simp.ok:
        outcome.simplified = False
        outcome.notes.append(f"simplify skipped: {simp.error}")
        append_loop_log(workspace, f"{title}: simplify FAILED ({simp.error}) — kept verified code")
        return

    write_artifact(workspace / "simplify" / f"{plan.worktree_name}.md", simp.output)

    # Behaviour-preservation guard: re-verify the simplified code.
    reverify = verifier.run(
        VERIFY_PROMPT.format(domain=domain, title=title),
        cwd=workspace,
        role="verifier",
    )
    if reverify.ok and _verdict_pass(reverify.output):
        outcome.simplified = True
        append_loop_log(workspace, f"{title}: simplified (behaviour preserved)")
    else:
        outcome.simplified = False
        outcome.notes.append("simplify reverted: re-verify did not pass")
        append_loop_log(workspace, f"{title}: simplify reverted — re-verify failed")


def _contradiction_flag(skills_dir: Path, ratcheted: Optional[Path]) -> Optional[Path]:
    """Return the CONTRADICTIONS.md path if the just-written skill flagged one."""
    if ratcheted is None or "⚠ CONTRADICTION" not in ratcheted.read_text():
        return None
    flag = skills_dir / "CONTRADICTIONS.md"
    return flag if flag.exists() else None


def run_loop(
    tasks: List[Task],
    workspace: Path,
    skills_dir: Path,
    max_cycles: int,
    make_implementer,
    make_verifier,
    make_logic_checker=None,
    gate: Optional[str] = None,
    make_test_writer=None,
    make_simplifier=None,
    make_advisor=None,
    advisor_rounds: int = 1,
    team: bool = False,
    max_workers: int = 3,
) -> List[CycleOutcome]:
    """Drive cycles until tasks are exhausted or the budget cap is hit.

    `make_implementer` / `make_verifier` are factories returning fresh, distinct
    AgentRunner instances per cycle (maker ≠ checker). `make_logic_checker`, when
    provided, adds a third distinct agent that grades logic/plan coherence — a
    cycle then passes only when both verify axes pass.

    `make_test_writer`, when provided (TDD mode), adds a distinct test-writer agent
    that pens a failing test before each implementer runs.

    `make_advisor`, when provided, adds a distinct advisor agent that escalates a
    verify/logic FAIL into a bounded correction-retry loop (see `execute_cycle`).

    `team`, when True, runs the (capped) batch of tasks CONCURRENTLY — independent
    tasks proceed in parallel, each its own full cycle. The recall snapshot is
    pre-built for every needed domain BEFORE fan-out, so the parallel phase only
    reads it (no races, deterministic). Sequential (default) preserves the original
    one-task-at-a-time behavior.

    `gate`, when set, is a wakeAgent script run once before the batch; if it
    reports nothing to do, the whole run is skipped (zero tokens).
    """
    if gate:
        from cli.gate import run_gate

        decision = run_gate(gate, cwd=workspace)
        if not decision.wake:
            append_loop_log(workspace, decision.reason)
            return []

    from cli.session_context import arch_context
    from cli.skills_recall import recall_lessons, render_recall_block

    # Select the capped batch up front (so recall can be pre-built for team mode).
    batch = incomplete_tasks(tasks)[:max_cycles]
    if len(incomplete_tasks(tasks)) > max_cycles:
        append_loop_log(workspace, f"budget cap reached ({max_cycles} cycles)")

    # Ground the amnesiac `claude -p` agents in the repo's architecture map (the
    # in-session plugin path gets it via the SessionStart hook; the CLI path does
    # not). Read ONCE from the project root and prepended to every domain's recall
    # block below. Empty when ARCHITECTURE.md is absent → no change (fail-safe).
    from cli.paths import project_root

    arch_block = arch_context(project_root())
    if arch_block:
        append_loop_log(workspace, "injected repo architecture map into agent prompts")

    # Pre-build the per-domain recall snapshot for the whole batch (one read per
    # domain). In team mode this MUST happen before fan-out so threads only read it.
    recall_cache: Dict[str, str] = {}
    for task in batch:
        domain = plan_cycle(task).implementer_domain
        if domain not in recall_cache:
            lessons = render_recall_block(recall_lessons(skills_dir, domain))
            # Architecture map first, then past lessons; either may be empty.
            combined = "\n\n".join(b for b in (arch_block, lessons) if b)
            recall_cache[domain] = combined
            if lessons:
                append_loop_log(workspace, f"recalled past lessons for domain '{domain}'")

    def run_one(task: Task) -> CycleOutcome:
        plan = plan_cycle(task)
        return execute_cycle(
            plan, workspace, skills_dir,
            make_implementer(), make_verifier(),
            make_logic_checker() if make_logic_checker else None,
            recall=recall_cache.get(plan.implementer_domain, ""),
            test_writer=make_test_writer() if make_test_writer else None,
            simplifier=make_simplifier() if make_simplifier else None,
            advisor=make_advisor() if make_advisor else None,
            advisor_rounds=advisor_rounds,
        )

    if team:
        # Independent tasks run concurrently; preserve batch order in results.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(run_one, batch))

    return [run_one(task) for task in batch]
