"""Loop engine: parse tasks, drive maker/checker cycles, ratchet failures.

Pure logic lives here (task parsing, cycle planning, ratchet rendering) so it is
fully testable without spawning real agents or worktrees. The CLI layer wires
this to real subprocesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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
