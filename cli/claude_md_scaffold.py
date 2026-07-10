"""Pure logic for scaffolding a best-practice-shaped CLAUDE.md / CLAUDE.local.md
starter (sigma:2026-07-10 deep-research pass).

Distinct from Claude Code's native `/init`: `/init` scans the repo with no
length/structure discipline and frequently produces bloated output (research
finding: repo-overview/architecture content is the most commonly auto-generated
content yet measurably doesn't improve task success). This scaffold instead
seeds the WHAT/WHY/HOW structure the research converges on, capped well under
the official ~200-line target, so a human fills in specifics rather than the
agent inventing prose to fill space.

Two targets:
  - "repo"  → CLAUDE.md (team-shared, committed to git)
  - "local" → CLAUDE.local.md (personal, gitignored)

The prompt asks an agent to walk the actual codebase and fill the skeleton with
real facts (commands, conventions, gotchas) — `skeleton()` alone is the static
fallback / dry-run preview, not what ships when an agent runs.
"""

from __future__ import annotations

from typing import Dict

_TARGETS: Dict[str, str] = {"repo": "CLAUDE.md", "local": "CLAUDE.local.md"}

_LENGTH_CAP = 200


def filename_for(target: str) -> str:
    """Map a scaffold target ("repo"/"local") to its real filename."""
    if target not in _TARGETS:
        raise ValueError(f"unknown scaffold target: {target!r} (expected 'repo' or 'local')")
    return _TARGETS[target]


def skeleton(project_name: str, target: str) -> str:
    """Render the static WHAT/WHY/HOW skeleton (fallback if the agent pass fails).

    Kept short and deliberately generic — the agent prompt asks for real facts;
    this is only what ships if that agent run produces nothing usable.
    """
    filename_for(target)  # validates target, raises on unknown
    scope = "team-shared instructions, committed to git" if target == "repo" \
        else "personal preferences for this repo only, gitignored"
    return "\n".join(
        [
            f"# {project_name}",
            "",
            f"<!-- {scope} -->",
            "",
            "## What",
            "<!-- tech stack, project structure — 2-3 lines, not a file-by-file map -->",
            "",
            "## Why",
            "<!-- purpose of this project / this part of it — 1-2 lines -->",
            "",
            "## How",
            "<!-- exact commands Claude can't guess, non-default conventions, -->",
            "<!-- gotchas. Only what would cause a mistake if removed. -->",
            "",
        ]
    )


_REPO_PROMPT = """Generate a starting CLAUDE.md for the project at {root}, following
this best-practice research (converged from official Anthropic docs + community
consensus + real-world examples from cloudflare/workers-sdk, vercel/ai, supabase,
humanlayer):

- Target UNDER {cap} lines. For every line you write, ask: would removing this
  cause Claude to make a mistake? If not, don't write it.
- Structure as WHAT (tech stack, project structure — pointers not prose) / WHY
  (purpose) / HOW (exact commands, non-default conventions, gotchas).
- INCLUDE: bash commands Claude can't guess, code style that differs from
  defaults, testing instructions, repo etiquette (branch naming, PR conventions),
  project-specific architectural decisions, dev-environment quirks, gotchas.
- EXCLUDE: anything discoverable by reading the code, standard language
  conventions, detailed API docs (link instead), long tutorials, file-by-file
  descriptions, self-evident practices ("write clean code").
- Use file:line pointers, never pasted code snippets (snippets go stale).
- Write in imperative voice ("use X"), not hedged suggestions ("we generally
  prefer X").
- This file is TEAM-SHARED (committed to git) — don't include personal
  preferences, only conventions the whole team follows.

Walk the actual codebase (commands in package manifests/Makefiles, existing
conventions, test runner) and fill the structure with REAL facts, not
placeholders. Emit only the markdown file content, nothing before or after."""

_LOCAL_PROMPT = """Generate a starting CLAUDE.local.md for the project at {root},
following this best-practice research (converged from official Anthropic docs +
community consensus + real-world examples):

- Target UNDER {cap} lines. For every line you write, ask: would removing this
  cause Claude to make a mistake? If not, don't write it.
- This file is PERSONAL (gitignored, never committed) — capture only things
  specific to this one developer's workflow on this machine: personal aliases,
  local env quirks, individual workflow preferences that would be inappropriate
  to force on the whole team via the shared CLAUDE.md.
- Do NOT duplicate anything that belongs in the team-shared CLAUDE.md (commands,
  conventions, architecture) — check if CLAUDE.md already exists at {root} and
  only add what's missing/personal.
- Write in imperative voice, use file:line pointers not pasted code.

Emit only the markdown file content, nothing before or after."""


def build_scaffold_prompt(root: str, target: str) -> str:
    """Build the agent prompt for scaffolding `target` ("repo" or "local") at `root`."""
    if target == "repo":
        return _REPO_PROMPT.format(root=root, cap=_LENGTH_CAP)
    if target == "local":
        return _LOCAL_PROMPT.format(root=root, cap=_LENGTH_CAP)
    raise ValueError(f"unknown scaffold target: {target!r} (expected 'repo' or 'local')")
