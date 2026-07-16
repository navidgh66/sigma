"""Confirm-gated upsert of the ARCHITECTURE.md reference line into CLAUDE.md.

CLAUDE.md is committed/shared (unlike gitignored CLAUDE.local.md), so unlike
`cli/claude_local.py`'s always-on refresh, writing here requires explicit
confirmation — the same rule RTK/caveman/statusline/graphify follow for
anything touching shared or committed state (see cli/statusline.py).

The reference is a single line: read ARCHITECTURE.md on demand (not loaded
into every session — cheap), falling back to `sigma learn` when it's missing.
Delimited by markers so re-running is idempotent (mirrors claude_local.py).
Only offered when CLAUDE.md already exists — `sigma learn` never creates one
(that is claude_md_scaffold's job) and never edits an existing CLAUDE.md
without asking (the standing rule from cli/claude_md_check.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

FILENAME = "CLAUDE.md"
START_MARKER = "<!-- sigma:architecture-ref:start -->"
END_MARKER = "<!-- sigma:architecture-ref:end -->"

REFERENCE = (
    "**Reference:** read `ARCHITECTURE.md` for the full architecture map. If it "
    "does not exist, run `sigma learn` (or `/sigma:learn`) to generate it first."
)


def has_reference(existing: str) -> bool:
    """True if the managed reference block is already present."""
    return START_MARKER in existing and END_MARKER in existing


def upsert_reference(existing: str) -> str:
    """Insert or replace the managed reference block, returning new text.

    Pure: builds and returns a new string, never mutates input. Idempotent —
    re-applying to output it already produced is a no-op change.
    """
    block = f"{START_MARKER}\n{REFERENCE}\n{END_MARKER}"
    start = existing.find(START_MARKER)
    end = existing.find(END_MARKER)
    if start != -1 and end != -1 and end > start:
        before = existing[:start]
        after = existing[end + len(END_MARKER):]
        return f"{before}{block}{after}"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    sep = "\n" if existing else ""
    return f"{existing}{sep}{block}\n"


def write_reference(root: Path) -> bool:
    """Upsert the reference block into root/CLAUDE.md. Returns True on success.

    Best-effort: any OSError yields False rather than raising. Caller ensures
    CLAUDE.md exists and the user has confirmed before calling this.
    """
    try:
        f = root / FILENAME
        existing = f.read_text() if f.exists() else ""
        f.write_text(upsert_reference(existing))
    except OSError:
        return False
    return True


def setup_claude_md_reference(
    root: Path,
    confirm: Optional[Callable[[str], bool]] = None,
) -> bool:
    """Confirm-gated, idempotent upsert. Returns True if it changed state.

    - No CLAUDE.md at all → no-op (learn doesn't create one; scaffold does).
    - Reference already present → no-op.
    - Otherwise → confirm, then upsert. Mirrors setup_statusline / setup_rtk:
      the user must approve before anything touches committed, shared state.
    """
    confirm = confirm or (lambda msg: False)
    f = root / FILENAME
    if not f.is_file():
        return False

    try:
        existing = f.read_text()
    except OSError:
        return False

    if has_reference(existing):
        return False

    if not confirm(
        "Add a one-line ARCHITECTURE.md reference to CLAUDE.md "
        "(committed, shared with your team)?"
    ):
        return False

    return write_reference(root)
