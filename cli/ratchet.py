"""Ratchet: write a lesson into skills/<slug>/SKILL.md (+ contradiction flag).

Shared by `sigma review` and the in-session /loop (which writes the same file
format). Pure apart from the file writes; the caller passes `created` (no clock
here) so rendering stays deterministic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "lesson"


def render_skill(
    failure_title: str, lesson: str, domain: Optional[str] = None, created: Optional[str] = None
) -> str:
    """Render a SKILL.md body that ratchets a failure into permanent knowledge."""
    # Quoted: the description contains ": " (and titles may too), which is invalid
    # in a plain YAML scalar. A JSON string is a valid YAML double-quoted scalar.
    description = json.dumps(f"Avoid recurrence of: {failure_title}", ensure_ascii=False)
    front = ["---", f"name: {_slug(failure_title)}", f"description: {description}"]
    meta = []
    if domain:
        meta.append(f"  domain: {domain}")
    if created:
        meta.append(f"  created: {created}")
    if meta:
        front.append("metadata:\n" + "\n".join(meta))
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


def flag_contradiction(
    skills_dir: Path, new_skill: Path, conflicts: List[Path], domain: Optional[str]
) -> Path:
    """Append a flag to skills/CONTRADICTIONS.md. Never resolves; humans decide."""
    flag = skills_dir / "CONTRADICTIONS.md"
    if not flag.exists():
        flag.write_text("# Contradictions (human review)\n\n")
    existing = ", ".join(str(p.relative_to(skills_dir)) for p in conflicts)
    with flag.open("a") as fh:
        fh.write(f"- [{domain or '-'}] {new_skill.relative_to(skills_dir)} vs {existing}\n")
    return flag


def ratchet_to_skills(
    skills_dir: Path,
    failure_title: str,
    lesson: str,
    domain: Optional[str] = None,
    created: Optional[str] = None,
) -> Path:
    """Write a ratcheted lesson into skills/ so the same mistake is not repeated.

    Before writing, check for an existing lesson on the same domain + topic. If
    found, flag a contradiction (in the new skill + a central CONTRADICTIONS.md)
    for human review; never auto-resolve or delete the existing lesson.
    """
    from cli.skills_index import find_contradictions, topic_key

    # Never overwrite an earlier lesson: a same-titled one gets a -2, -3 ... suffix,
    # so the older lesson survives as evidence for the contradiction flag below.
    slug = _slug(failure_title)
    target = skills_dir / slug
    n = 2
    while (target / "SKILL.md").exists():
        target = skills_dir / f"{slug}-{n}"
        n += 1
    target.mkdir(parents=True, exist_ok=True)
    out = target / "SKILL.md"

    conflicts = find_contradictions(skills_dir, domain, topic_key(failure_title))
    body = render_skill(failure_title, lesson, domain, created)
    if conflicts:
        marker = (
            "\n> ⚠ CONTRADICTION: this lesson may conflict with "
            + ", ".join(str(p.relative_to(skills_dir)) for p in conflicts)
            + ", human review needed.\n"
        )
        body = body + marker
        flag_contradiction(skills_dir, out, conflicts, domain)
    out.write_text(body)
    return out
