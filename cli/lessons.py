"""Lesson-efficacy projection — close the loop on the learning loop.

Ratcheting is write-only: lessons accumulate in `skills/` forever and recall
quality degrades as noise builds. This module reads BOTH sides back —
role="cycle" trajectory steps (which carry the cycle's domain + the lesson
slugs recalled into its prompts) and the domain-tagged lessons on disk — and
correlates them:

  - WORKING:     recalled into ≥1 cycle, pass rate ≥ 50%;
  - NOT WORKING: recalled into ≥1 cycle, pass rate < 50% — the domain keeps
                 failing despite the lesson; surface it for a human rewrite;
  - NO EVIDENCE: never seen in any cycle's recall (domain idle, or the lesson
                 was truncated out by the recall cap) — archive CANDIDATE only.

Laws (same as `sigma prune`): never act on absent evidence — with zero
recall-carrying cycle steps there are NO archive candidates, only a note; and
archive ≠ delete — `archive_lesson` MOVES a lesson dir to `skills/archive/`
(excluded from recall by the domain scan) and is trivially reversible.

Deterministic read-model: no clock, no agent, no confirmation — the CLI layer
owns prompts. (`efficacy` fills counters on the LessonStats it is given.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from cli.skills_index import parse_skill_meta
from cli.trajectory import TrajectoryStep

ARCHIVE_DIR = "archive"
# Below this pass rate a recalled lesson is surfaced as not-working.
WORKING_THRESHOLD = 0.5


@dataclass
class LessonStats:
    slug: str
    domain: Optional[str]
    recalled: int = 0
    passed: int = 0

    @property
    def pass_rate(self) -> Optional[float]:
        return (self.passed / self.recalled) if self.recalled else None


@dataclass
class EfficacyReport:
    working: List[LessonStats] = field(default_factory=list)
    not_working: List[LessonStats] = field(default_factory=list)
    no_evidence: List[LessonStats] = field(default_factory=list)
    cycles_seen: int = 0

    @property
    def has_recall_evidence(self) -> bool:
        return self.cycles_seen > 0


def list_domain_lessons(skills_dir: Path) -> List[LessonStats]:
    """Every domain-tagged lesson on disk (excluding the archive), zero-counted.

    Domain-less skills (vendor / sigma-*) are excluded — they are not ratcheted
    lessons and never enter recall.
    """
    if not skills_dir.exists():
        return []
    out: List[LessonStats] = []
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        if ARCHIVE_DIR in skill_md.relative_to(skills_dir).parts:
            continue
        domain = parse_skill_meta(skill_md).get("domain")
        if not domain:
            continue
        out.append(LessonStats(slug=skill_md.parent.name, domain=domain))
    return out


def efficacy(steps: List[TrajectoryStep], lessons: List[LessonStats]) -> EfficacyReport:
    """Fold cycle steps into per-lesson recall/pass counts and bucket them."""
    by_slug: Dict[str, LessonStats] = {le.slug: le for le in lessons}
    cycles = [s for s in steps if s.role == "cycle" and s.lessons is not None]
    for step in cycles:
        for slug in step.lessons or []:
            stats = by_slug.get(slug)
            if stats is None:
                # Recalled once but since archived/removed — still counts as
                # evidence for the run it served, but nothing to bucket now.
                continue
            stats.recalled += 1
            if step.ok:
                stats.passed += 1

    report = EfficacyReport(cycles_seen=len(cycles))
    for stats in by_slug.values():
        if stats.recalled == 0:
            report.no_evidence.append(stats)
        elif (stats.pass_rate or 0.0) >= WORKING_THRESHOLD:
            report.working.append(stats)
        else:
            report.not_working.append(stats)
    return report


def archive_lesson(skills_dir: Path, slug: str) -> Optional[Path]:
    """MOVE a lesson dir into skills/archive/ (reversible; never a delete).

    Returns the new path, or None when the lesson doesn't exist or the target
    is already taken (never overwrites — surface, don't clobber).
    """
    src = skills_dir / slug
    if not src.is_dir():
        return None
    dest = skills_dir / ARCHIVE_DIR / slug
    if dest.exists():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)
    return dest


def render_report(report: EfficacyReport) -> str:
    """Human-readable efficacy report."""
    lines = ["# sigma lessons — efficacy", ""]
    if not report.has_recall_evidence:
        lines += [
            "No recall-carrying cycle steps found in this workspace yet. Run "
            "`sigma loop --execute` (cycles record which lessons they recalled) "
            "— no archive candidates are suggested on absent evidence.",
        ]
        return "\n".join(lines)

    lines.append(f"Evidence: {report.cycles_seen} cycle(s) with recall provenance.")
    lines.append("")

    def _bucket(title: str, items: List[LessonStats], note: str) -> None:
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("- (none)")
        for st in sorted(items, key=lambda s: s.slug):
            rate = f"{st.pass_rate:.0%}" if st.pass_rate is not None else "n/a"
            lines.append(f"- **{st.slug}** [{st.domain}] — recalled {st.recalled}×, pass rate {rate}")
        if note:
            lines.append(f"\n_{note}_")
        lines.append("")

    _bucket("Working", report.working,
            "Recalled and the cycles pass — keep.")
    _bucket("Not working", report.not_working,
            "Recalled but cycles keep failing — rewrite the lesson; it is not "
            "preventing the mistake it records. Never auto-edited.")
    _bucket("No usage evidence", report.no_evidence,
            "Never recalled in the scanned cycles (idle domain or recall-cap "
            "truncation). Archive candidates — `sigma lessons --archive` moves "
            "them to skills/archive/ (reversible), only with per-lesson confirm.")
    return "\n".join(lines)
