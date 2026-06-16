"""Loop engine: parse tasks, drive maker/checker cycles, ratchet failures.

Pure logic lives here (task parsing, cycle planning, ratchet rendering) so it is
fully testable without spawning real agents or worktrees. The CLI layer wires
this to real subprocesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

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
    """Write a ratcheted lesson into skills/ so the loop never repeats it."""
    slug = re.sub(r"[^a-z0-9]+", "-", failure_title.lower()).strip("-") or "lesson"
    target = skills_dir / slug
    target.mkdir(parents=True, exist_ok=True)
    out = target / "SKILL.md"
    out.write_text(render_skill(failure_title, lesson, domain))
    return out


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


@dataclass
class CycleOutcome:
    task_title: str
    implemented: bool
    verified: bool
    ratcheted_skill: Optional[Path] = None
    notes: List[str] = field(default_factory=list)


def _verdict_pass(verify_output: str) -> bool:
    """Parse the checker's verdict line. Defaults to FAIL if absent (skeptical)."""
    for line in reversed(verify_output.splitlines()):
        line = line.strip().upper()
        if line.startswith("VERDICT:"):
            return "PASS" in line
    return False


def execute_cycle(
    plan: CyclePlan,
    workspace: Path,
    skills_dir: Path,
    implementer: AgentRunner,
    verifier: AgentRunner,
) -> CycleOutcome:
    """Run one maker→checker cycle. On failure, ratchet a lesson into skills/.

    `implementer` and `verifier` MUST be distinct runner instances (maker ≠
    checker). They are injectable, so this is testable with fakes.
    """
    if implementer is verifier:
        raise ValueError("maker and checker must be distinct agents")

    title = plan.task.title
    domain = plan.implementer_domain
    outcome = CycleOutcome(task_title=title, implemented=False, verified=False)

    impl = implementer.run(IMPLEMENT_PROMPT.format(domain=domain, title=title), cwd=workspace)
    outcome.implemented = impl.ok
    if not impl.ok:
        outcome.notes.append(f"implement failed: {impl.error}")
        outcome.ratcheted_skill = ratchet_to_skills(
            skills_dir, f"implement failed: {title}", impl.error or "unknown", domain
        )
        append_loop_log(workspace, f"{title}: implement FAILED ({impl.error})")
        return outcome

    write_artifact(workspace / "impl" / f"{plan.worktree_name}.md", impl.output)

    chk = verifier.run(VERIFY_PROMPT.format(domain=domain, title=title), cwd=workspace)
    write_artifact(workspace / "verify" / f"{plan.worktree_name}.md", chk.output)
    passed = chk.ok and _verdict_pass(chk.output)
    outcome.verified = passed

    if passed:
        append_loop_log(workspace, f"{title}: PASS")
    else:
        reason = chk.error if not chk.ok else "verifier returned VERDICT: FAIL"
        outcome.notes.append(f"verify failed: {reason}")
        outcome.ratcheted_skill = ratchet_to_skills(
            skills_dir, f"verify failed: {title}", reason, domain
        )
        append_loop_log(workspace, f"{title}: verify FAILED ({reason})")
    return outcome


def run_loop(
    tasks: List[Task],
    workspace: Path,
    skills_dir: Path,
    max_cycles: int,
    make_implementer,
    make_verifier,
) -> List[CycleOutcome]:
    """Drive cycles until tasks are exhausted or the budget cap is hit.

    `make_implementer` / `make_verifier` are factories returning fresh, distinct
    AgentRunner instances per cycle (maker ≠ checker).
    """
    outcomes: List[CycleOutcome] = []
    completed = 0
    for task in incomplete_tasks(tasks):
        if completed >= max_cycles:
            append_loop_log(workspace, f"budget cap reached ({max_cycles} cycles)")
            break
        plan = plan_cycle(task)
        outcome = execute_cycle(
            plan, workspace, skills_dir, make_implementer(), make_verifier()
        )
        outcomes.append(outcome)
        completed += 1
    return outcomes
