"""Upsert a sigma-managed pointer block into CLAUDE.local.md (static fallback).

CLAUDE.local.md is gitignored and auto-loaded into every Claude Code session. It
is the static counterpart to the SessionStart hook: environments without hooks
still see the learn pointer here. `sigma learn` refreshes this block after writing
its artifacts so the pointer stays honest.

`upsert_block` is a pure string transform (insert or replace between markers,
immutable build); `write_block` is the thin filesystem side. Both are idempotent
and best-effort — a failed write is never fatal to `sigma learn` (same fail-safe
discipline as the graphify build).
"""

from __future__ import annotations

from pathlib import Path

LOCAL_FILENAME = "CLAUDE.local.md"
START_MARKER = "<!-- sigma:learn:start -->"
END_MARKER = "<!-- sigma:learn:end -->"


def upsert_block(existing: str, pointer: str) -> str:
    """Insert or replace the sigma-managed block within `existing`, returning new text.

    If the markers are already present, the content between them is replaced;
    otherwise the block is appended. Pure: builds and returns a new string,
    never mutates input. Idempotent when `pointer` is unchanged.
    """
    block = f"{START_MARKER}\n{pointer}\n{END_MARKER}"
    start = existing.find(START_MARKER)
    end = existing.find(END_MARKER)
    if start != -1 and end != -1 and end > start:
        before = existing[:start]
        after = existing[end + len(END_MARKER):]
        return f"{before}{block}{after}"
    # Append, keeping a blank line of separation from any prior content.
    if existing and not existing.endswith("\n"):
        existing += "\n"
    sep = "\n" if existing else ""
    return f"{existing}{sep}{block}\n"


def _ensure_gitignored(root: Path) -> None:
    """Add CLAUDE.local.md to .gitignore if not already present (best-effort)."""
    gi = root / ".gitignore"
    try:
        text = gi.read_text() if gi.exists() else ""
        lines = {ln.strip() for ln in text.splitlines()}
        if LOCAL_FILENAME in lines:
            return
        if text and not text.endswith("\n"):
            text += "\n"
        gi.write_text(f"{text}{LOCAL_FILENAME}\n")
    except OSError:
        pass


def write_block(root: Path, pointer: str) -> bool:
    """Upsert the pointer block into root/CLAUDE.local.md; ensure it's gitignored.

    Returns True on success. Best-effort: any OSError (e.g. root is not a
    directory) yields False rather than raising, so `sigma learn` never fails
    because the static fallback couldn't be written.
    """
    try:
        f = root / LOCAL_FILENAME
        existing = f.read_text() if f.exists() else ""
        f.write_text(upsert_block(existing, pointer))
    except OSError:
        return False
    _ensure_gitignored(root)
    return True
