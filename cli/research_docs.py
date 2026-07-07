"""Pure render functions: generate the shared-rules markdown block embedded in
commands/research.md and the persona docs, from cli/research_brief.RULES_TEXT.

Regenerate with scripts/regen_research_docs.py after editing research_brief.py.
tests/test_research_docs.py locks the checked-in files to these renders so the
two surfaces (CLI briefs vs in-session docs) never silently drift apart.
"""

from __future__ import annotations

from cli.research_brief import RULES_TEXT

MARKER_START = "<!-- sigma:research-rules:start -->"
MARKER_END = "<!-- sigma:research-rules:end -->"


def render_command_rules_block() -> str:
    """The generated rules block for commands/research.md's Rules section."""
    lines = ["Every researcher/tool follows the same rules:", ""]
    lines.extend(RULES_TEXT.splitlines())
    return "\n".join(lines)


def render_persona_rules_block() -> str:
    """The generated rules block for each surviving persona doc's Return section."""
    return RULES_TEXT
