"""Recall ratcheted lessons into a future run — the read side of the loop.

`cli/loop.py` writes a lesson to `skills/<slug>/SKILL.md` on failure (tagged with
`metadata: domain:`). This module reads them back: given a domain, it selects the
lessons for that domain and renders a compact block to prepend to the next run's
prompt — so the loop (and in-session work via the `sigma-lessons` skill) actually
*applies* past mistakes instead of only recording them.

Pure and deterministic: it only reads the skills tree (no agent, no mutation).
Selection is by domain match (reuses `skills_index.parse_skill_meta`); lessons
without a `domain:` (vendor / sigma-present / sigma-domains skills) are excluded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from cli.skills_index import parse_skill_meta

# Default cap on lessons injected into one prompt (bounds prompt size). The
# caller is told (via the returned `truncated` flag) when lessons were dropped.
DEFAULT_LIMIT = 12

_TITLE_RE = re.compile(r"^#\s+(.*)$")
_LESSON_RE = re.compile(r"^\*\*Lesson \(ratcheted\):\*\*\s*(.*)$")
_APPLY_RE = re.compile(r"^\*\*How to apply:\*\*\s*(.*)$")


@dataclass
class Lesson:
    """A ratcheted lesson resolved for recall."""

    path: Path
    domain: Optional[str]
    title: str
    lesson: str = ""
    how_to_apply: str = ""


@dataclass
class Recall:
    """Result of a recall: the selected lessons + whether any were dropped."""

    lessons: List[Lesson]
    truncated: bool = False


def _parse_lesson_body(skill_md: Path, domain: Optional[str], title: str) -> Lesson:
    """Pull the lesson + how-to-apply lines from a ratcheted SKILL.md body."""
    lesson = ""
    how = ""
    try:
        for line in skill_md.read_text().splitlines():
            m = _LESSON_RE.match(line.strip())
            if m:
                lesson = m.group(1).strip()
                continue
            m = _APPLY_RE.match(line.strip())
            if m:
                how = m.group(1).strip()
    except OSError:
        pass
    return Lesson(path=skill_md, domain=domain, title=title, lesson=lesson, how_to_apply=how)


def _title_of(skill_md: Path) -> str:
    """First `# heading` of a SKILL.md, else the parent dir name."""
    try:
        for line in skill_md.read_text().splitlines():
            m = _TITLE_RE.match(line.strip())
            if m and m.group(1).strip():
                return m.group(1).strip()
    except OSError:
        pass
    return skill_md.parent.name


def recall_lessons(
    skills_dir: Path, domain: Optional[str], limit: int = DEFAULT_LIMIT
) -> Recall:
    """Select ratcheted lessons whose `domain:` matches `domain`.

    Lessons without a domain are excluded (so vendor / sigma-present /
    sigma-domains skills never leak in). Deterministic order (sorted path).
    Returns at most `limit` lessons and flags truncation.
    """
    if not domain or not skills_dir.exists():
        return Recall(lessons=[], truncated=False)
    selected: List[Lesson] = []
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        meta = parse_skill_meta(skill_md)
        if meta.get("domain") != domain:
            continue
        title = _title_of(skill_md)
        selected.append(_parse_lesson_body(skill_md, domain, title))
    truncated = len(selected) > limit
    return Recall(lessons=selected[:limit], truncated=truncated)


def render_recall_block(recall: Recall) -> str:
    """Render selected lessons as a compact 'avoid repeating' prompt block.

    Empty recall → "" (caller prepends nothing; prompts stay byte-identical to
    the no-lessons case).
    """
    if not recall.lessons:
        return ""
    lines: List[str] = ["--- past lessons (avoid repeating these mistakes) ---"]
    for lesson in recall.lessons:
        lines.append(f"- {lesson.title}")
        if lesson.lesson:
            lines.append(f"    lesson: {lesson.lesson}")
        if lesson.how_to_apply:
            lines.append(f"    apply: {lesson.how_to_apply}")
    if recall.truncated:
        lines.append("- (older lessons omitted — most recent shown)")
    lines.append("--- end past lessons ---")
    return "\n".join(lines)
