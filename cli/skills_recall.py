"""Recall ratcheted lessons into a future run: the read side of the learning loop.

`/loop` (on a failed task), `sigma review` and `/sigma-learn-lesson` write lessons
to `skills/<slug>/SKILL.md` (tagged `metadata: domain:` and `created:`). This module
reads them back: given a domain, it selects at most `DEFAULT_LIMIT` lessons, newest
first, and renders a compact block to prepend to the next prompt.

The cap is deliberately small: large skill libraries measurably hurt agents (wrong
skill picked), so recall favours the few most recent lessons.

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
DEFAULT_LIMIT = 5

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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
    created: Optional[str] = None  # YYYY-MM-DD from metadata, None if absent/malformed


@dataclass
class Recall:
    """Result of a recall: the selected lessons + whether any were dropped."""

    lessons: List[Lesson]
    truncated: bool = False


def _read_lesson(skill_md: Path, domain: Optional[str]) -> Lesson:
    """Read a ratcheted SKILL.md ONCE → title + lesson + how-to-apply.

    Title is the first `# heading` (else the parent dir name). On OSError, returns
    a Lesson titled by the dir name with empty fields (defensive, never raises).
    """
    title = ""
    lesson = ""
    how = ""
    try:
        for line in skill_md.read_text().splitlines():
            s = line.strip()
            if not title:
                m = _TITLE_RE.match(s)
                if m and m.group(1).strip():
                    title = m.group(1).strip()
            m = _LESSON_RE.match(s)
            if m:
                lesson = m.group(1).strip()
                continue
            m = _APPLY_RE.match(s)
            if m:
                how = m.group(1).strip()
    except OSError:
        pass
    return Lesson(
        path=skill_md,
        domain=domain,
        title=title or skill_md.parent.name,
        lesson=lesson,
        how_to_apply=how,
    )


def recall_lessons(
    skills_dir: Path, domain: Optional[str], limit: int = DEFAULT_LIMIT
) -> Recall:
    """Select ratcheted lessons whose `domain:` matches `domain`.

    Lessons without a domain are excluded (so vendor / sigma-present /
    sigma-domains skills never leak in). Order: dated lessons newest first (ties
    by path), then undated or malformed-date lessons by path. Returns at most
    `limit` lessons and flags truncation.
    """
    if not domain or not skills_dir.exists():
        return Recall(lessons=[], truncated=False)
    selected: List[Lesson] = []
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        # skills/archive/ holds lessons a human retired by hand: excluded from
        # recall, still on disk and trivially restorable.
        if "archive" in skill_md.relative_to(skills_dir).parts:
            continue
        meta = parse_skill_meta(skill_md)
        if meta.get("domain") != domain:
            continue
        lesson = _read_lesson(skill_md, domain)
        created = meta.get("created") or ""
        lesson.created = created if _DATE_RE.match(created) else None
        selected.append(lesson)
    # `selected` is in path order; a STABLE sort puts dated lessons newest first
    # (ties keep path order), then undated/malformed ones follow in path order.
    dated = [le for le in selected if le.created]
    undated = [le for le in selected if not le.created]
    dated.sort(key=lambda le: le.created, reverse=True)
    ordered = dated + undated
    truncated = len(ordered) > limit
    return Recall(lessons=ordered[:limit], truncated=truncated)


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
        lines.append(f"- (more lessons omitted, showing newest {len(recall.lessons)})")
    lines.append("--- end past lessons ---")
    return "\n".join(lines)
