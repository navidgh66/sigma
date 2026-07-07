#!/usr/bin/env python3
"""Regenerate the shared-rules blocks in commands/research.md and the
surviving persona docs from cli/research_brief.py. Run manually after editing
research_brief.py's RULES_TEXT.

Usage: python3 scripts/regen_research_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.research_docs import (  # noqa: E402
    MARKER_END,
    MARKER_START,
    render_command_rules_block,
    render_persona_rules_block,
)

ROOT = Path(__file__).resolve().parent.parent
_BLOCK_RE = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END), re.DOTALL
)


def _replace_block(path: Path, new_block_body: str) -> None:
    text = path.read_text()
    replacement = f"{MARKER_START}\n{new_block_body}\n{MARKER_END}"
    if not _BLOCK_RE.search(text):
        raise SystemExit(f"{path}: no {MARKER_START}...{MARKER_END} block found")
    path.write_text(_BLOCK_RE.sub(replacement, text))


def main() -> None:
    _replace_block(ROOT / "commands" / "research.md", render_command_rules_block())
    for name in ("gemini-researcher.md", "gpt-researcher.md"):
        _replace_block(ROOT / "subagents" / "researchers" / name, render_persona_rules_block())
    print("regenerated research docs from cli/research_brief.py")


if __name__ == "__main__":
    main()
