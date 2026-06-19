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


@dataclass
class CycleOutcome:
    task_title: str
    implemented: bool
    verified: bool
    logic_ok: Optional[bool] = None
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
) -> CycleOutcome:
    """Run one maker→checker cycle. On failure, ratchet a lesson into skills/.

    `implementer` and `verifier` MUST be distinct runner instances (maker ≠
    checker). They are injectable, so this is testable with fakes.

    When `logic_checker` is provided it runs a SECOND, independent verify axis:
    the logic evaluator grades reasoning + plan-coherence (not code quality). It
    must be distinct from both implementer and verifier. The cycle passes only
    when BOTH the code-quality verifier and the logic evaluator pass.

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

    title = plan.task.title
    domain = plan.implementer_domain
    outcome = CycleOutcome(task_title=title, implemented=False, verified=False)

    impl = implementer.run(
        _with_recall(IMPLEMENT_PROMPT.format(domain=domain, title=title), recall),
        cwd=workspace,
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

    chk = verifier.run(
        _with_recall(VERIFY_PROMPT.format(domain=domain, title=title), recall),
        cwd=workspace,
    )
    write_artifact(workspace / "verify" / f"{plan.worktree_name}.md", chk.output)
    quality_passed = chk.ok and _verdict_pass(chk.output)

    # Second axis: logic evaluator (optional, independent agent).
    logic_passed = True
    if logic_checker is not None:
        logic = logic_checker.run(LOGIC_PROMPT.format(domain=domain, title=title), cwd=workspace)
        write_artifact(workspace / "verify" / f"{plan.worktree_name}.logic.md", logic.output)
        logic_passed = logic.ok and _verdict_pass(logic.output)
        outcome.logic_ok = logic_passed

    passed = quality_passed and logic_passed
    outcome.verified = passed

    if passed:
        append_loop_log(workspace, f"{title}: PASS")
    else:
        if not quality_passed:
            reason = chk.error if not chk.ok else "verifier returned VERDICT: FAIL"
        else:
            reason = "logic evaluator returned VERDICT: FAIL"
        outcome.notes.append(f"verify failed: {reason}")
        outcome.ratcheted_skill = ratchet_to_skills(
            skills_dir, f"verify failed: {title}", reason, domain
        )
        outcome.contradiction = _contradiction_flag(skills_dir, outcome.ratcheted_skill)
        append_loop_log(workspace, f"{title}: verify FAILED ({reason})")
    return outcome


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
) -> List[CycleOutcome]:
    """Drive cycles until tasks are exhausted or the budget cap is hit.

    `make_implementer` / `make_verifier` are factories returning fresh, distinct
    AgentRunner instances per cycle (maker ≠ checker). `make_logic_checker`, when
    provided, adds a third distinct agent that grades logic/plan coherence — a
    cycle then passes only when both verify axes pass.

    `gate`, when set, is a wakeAgent script run once before the batch; if it
    reports nothing to do, the whole run is skipped (zero tokens).
    """
    if gate:
        from cli.gate import run_gate

        decision = run_gate(gate, cwd=workspace)
        if not decision.wake:
            append_loop_log(workspace, decision.reason)
            return []

    from cli.skills_recall import recall_lessons, render_recall_block

    recall_cache: Dict[str, str] = {}

    def recall_for(domain: str) -> str:
        """Past-lessons block for a domain, built once per domain and cached for
        the batch. Cached for the whole run, so a lesson ratcheted by a failed
        cycle this batch surfaces on the NEXT RUN, not later same-domain tasks in
        this batch (the cache is intentionally not invalidated mid-batch — recall
        is a per-batch snapshot, keeping cost bounded and behavior deterministic).
        """
        if domain not in recall_cache:
            block = render_recall_block(recall_lessons(skills_dir, domain))
            recall_cache[domain] = block
            if block:
                append_loop_log(workspace, f"recalled past lessons for domain '{domain}'")
        return recall_cache[domain]

    outcomes: List[CycleOutcome] = []
    completed = 0
    for task in incomplete_tasks(tasks):
        if completed >= max_cycles:
            append_loop_log(workspace, f"budget cap reached ({max_cycles} cycles)")
            break
        plan = plan_cycle(task)
        logic = make_logic_checker() if make_logic_checker else None
        outcome = execute_cycle(
            plan, workspace, skills_dir, make_implementer(), make_verifier(), logic,
            recall=recall_for(plan.implementer_domain),
        )
        outcomes.append(outcome)
        completed += 1
    return outcomes
