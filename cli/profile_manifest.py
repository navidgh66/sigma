"""Pure logic for the sigma logic-profile — the living record of a codebase's
invariants that grounds `sigma review` / `/review`.

The profile is a single markdown file (`sigma/profile/logic-profile.md`) with two
sections: **ML-logic** invariants (splits, leakage guards, metrics, reward shaping,
eval determinism) and **system-logic** invariants (control flow, data contracts,
concurrency, state, API boundaries). It is built by a dedicated walker
(`cli/profile_run.py` / `/profile`) and refreshed manually; this module owns the
parts that must be testable without spawning an agent:

  - the skeleton contract the walker fills in (so a test pins the section shape),
  - `validate_profile` — a structural guard (both sections present, non-empty),
  - `staleness` — flag a profile older than the files about to be reviewed.

Pure and deterministic: no subprocess, no timestamp generated here (callers pass
file lists / mtimes in), mirroring the discipline in `board.Event.ts` and
`weave_manifest.build_manifest`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# The two mandatory section headers. The walker must emit both; the review side
# reads the whole file, but these anchors let a test assert the contract.
ML_LOGIC_HEADER = "## ML-logic invariants"
SYSTEM_LOGIC_HEADER = "## System-logic invariants"

PROFILE_DIRNAME = "profile"
PROFILE_FILENAME = "logic-profile.md"


def profile_path(project_root: Path) -> Path:
    """Where the logic profile lives for a project."""
    return project_root / "sigma" / PROFILE_DIRNAME / PROFILE_FILENAME


def profile_skeleton(project_name: str) -> str:
    """Render the empty profile skeleton the walker fills in.

    Kept here (not in the prompt) so the section contract is testable and the
    walker + validator agree on one shape.
    """
    return "\n".join(
        [
            f"# Logic profile: {project_name}",
            "",
            "*A living record of this codebase's invariants. Refresh after logic "
            "changes (`/profile` or `sigma profile`). `review` reads this as "
            "grounding and flags it stale when older than the files under review.*",
            "",
            ML_LOGIC_HEADER,
            "",
            "<!-- splits, leakage guards, metrics, reward shaping, eval "
            "determinism — name real files. -->",
            "",
            SYSTEM_LOGIC_HEADER,
            "",
            "<!-- control flow, data contracts, concurrency, state, API "
            "boundaries — name real files. -->",
            "",
        ]
    )


def validate_profile(text: str) -> List[str]:
    """Structural guard: both sections present and each has some body.

    Returns a list of problems (empty == well-formed). Never raises; this is the
    inverse of a hard gate — the review side degrades gracefully on a bad profile.
    """
    problems: List[str] = []
    if ML_LOGIC_HEADER not in text:
        problems.append(f"missing section: {ML_LOGIC_HEADER!r}")
    if SYSTEM_LOGIC_HEADER not in text:
        problems.append(f"missing section: {SYSTEM_LOGIC_HEADER!r}")
    if ML_LOGIC_HEADER in text and SYSTEM_LOGIC_HEADER in text:
        # Section order matters: the body-slicing in `_section_body` assumes
        # ML-logic precedes system-logic. An inverted profile would slice the
        # wrong bodies and look valid — catch it here.
        if text.index(ML_LOGIC_HEADER) >= text.index(SYSTEM_LOGIC_HEADER):
            problems.append("section order inverted: ML-logic must precede system-logic")
        else:
            ml_body = _section_body(text, ML_LOGIC_HEADER, SYSTEM_LOGIC_HEADER)
            sys_body = _section_body(text, SYSTEM_LOGIC_HEADER, None)
            if not _has_content(ml_body):
                problems.append("ML-logic section is empty")
            if not _has_content(sys_body):
                problems.append("system-logic section is empty")
    return problems


def _section_body(text: str, start: str, end: Optional[str]) -> str:
    """Slice the body between two headers (end=None → to end of text)."""
    after = text.split(start, 1)[1] if start in text else ""
    if end and end in after:
        after = after.split(end, 1)[0]
    return after


def _has_content(body: str) -> bool:
    """True if a section body has a non-comment, non-blank line."""
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("<!--"):
            continue
        return True
    return False


@dataclass
class Staleness:
    """Result of a profile freshness check."""

    stale: bool
    profile_exists: bool
    newest_file: Optional[str] = None

    def banner(self) -> str:
        """A one-line warning to inject into review prompts (empty when fresh).

        Fail-safe by design: staleness only warns — it never blocks the review
        (Q3 freshness=2). A missing profile yields a distinct banner so the review
        side can degrade to lessons + diff only.
        """
        if not self.profile_exists:
            return (
                "⚠ no logic profile found — reviewing against diff + lessons only. "
                "Run `/profile` to ground future reviews."
            )
        if self.stale:
            extra = f" (e.g. {self.newest_file})" if self.newest_file else ""
            return (
                "⚠ logic profile is OLDER than the files under review"
                f"{extra} — invariants may be out of date. Consider `/profile`."
            )
        return ""


def staleness(profile: Path, touched_files: List[Path]) -> Staleness:
    """Flag the profile as stale if any touched file is newer than it.

    Uses mtime (cheap, deterministic given a fixed filesystem). Missing profile →
    `profile_exists=False`. A touched file that does not exist (deleted in the
    diff) is skipped. Never raises on a stat error — treats it as not-newer.
    """
    if not profile.exists():
        return Staleness(stale=False, profile_exists=False)

    try:
        profile_mtime = profile.stat().st_mtime
    except OSError:
        # Exists but unreadable (race / permissions) — treat as not-available so
        # the banner tells the reviewer grounding is missing, not "all clear".
        return Staleness(stale=False, profile_exists=False)

    newest: Optional[str] = None
    newest_mtime = profile_mtime
    for f in touched_files:
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        if mt > newest_mtime:
            newest_mtime = mt
            newest = str(f)
    return Staleness(stale=newest is not None, profile_exists=True, newest_file=newest)
