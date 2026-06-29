"""Build the session-start pointer to learn artifacts — the read side of `learn`.

`sigma learn` writes two durable artifacts (ARCHITECTURE.md + .tours/<slug>.tour)
but nothing fed them back into a Claude Code session. This module closes that
loop: `build_pointer` names whichever artifacts exist so a SessionStart hook (and
the static CLAUDE.local.md block) can nudge every new session to read them BEFORE
doing deep work. When nothing has been learned yet, it returns a lazy hint to run
`/learn` instead — so the hook always emits something useful.

Pure and deterministic: it only stats the project tree (no agent, no mutation, no
clock). It NEVER raises — a pathological tree degrades to the lazy hint, because a
session-start hook must never break a session (the same fail-safe posture as
`cli/gate.py` defaulting WAKE and `report_block` degrading to empty).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

ARCH_FILENAME = "ARCHITECTURE.md"
TOURS_DIRNAME = ".tours"

# Emitted when no learn artifact exists yet — the lazy fallback so a session that
# skipped `sigma learn` (or onboard) still gets nudged on every start.
LAZY_HINT = (
    "sigma: no architecture map yet — run /learn (or `sigma learn`) to ground "
    "future sessions in this repo."
)


def _find_tours(root: Path) -> List[str]:
    """Return sorted relative paths of .tours/*.tour files (empty if none/bad)."""
    tours_dir = root / TOURS_DIRNAME
    try:
        if not tours_dir.is_dir():
            return []
        rel = sorted(f"{TOURS_DIRNAME}/{p.name}" for p in tours_dir.glob("*.tour"))
        return rel
    except OSError:
        return []


def build_pointer(root: Path) -> str:
    """Build a pointer block naming the durable learn artifacts under `root`.

    Returns a short Markdown block listing ARCHITECTURE.md and any
    .tours/*.tour that exist, instructing the agent to read them before deep
    work. If neither exists (or the tree is unreadable), returns `LAZY_HINT`.
    Always non-empty; never raises.
    """
    try:
        has_arch = (root / ARCH_FILENAME).is_file()
        tours = _find_tours(root)
    except OSError:
        return LAZY_HINT

    if not has_arch and not tours:
        return LAZY_HINT

    lines: List[str] = ["sigma: this repo has durable learn artifacts — read before deep work:"]
    if has_arch:
        lines.append(f"- {ARCH_FILENAME} — architecture map (entry points, layout, conventions)")
    for tour in tours:
        lines.append(f"- {tour} — CodeTour walkthrough (open with the CodeTour extension)")
    return "\n".join(lines)
