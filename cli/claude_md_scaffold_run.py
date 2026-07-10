"""`sigma claude-md create` — scaffold a best-practice-shaped CLAUDE.md /
CLAUDE.local.md via an agent walk of the real codebase.

Wires the pure prompt/skeleton logic (`cli/claude_md_scaffold.py`) to a real
agent: build the prompt, run it, write the result (falling back to the static
skeleton if the agent fails or returns nothing usable — same fail-safe shape as
`cli/profile_run.py`). Refuses to clobber an existing file unless `force=True`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cli.claude_md_scaffold import build_scaffold_prompt, filename_for, skeleton
from cli.runner import AgentRunner, write_artifact


@dataclass
class ScaffoldResult:
    ok: bool
    path: Optional[Path] = None
    used_skeleton_fallback: bool = False
    prompt: str = ""
    error: Optional[str] = None


def run_scaffold(
    root: Path,
    target: str,
    agent: Optional[AgentRunner] = None,
    force: bool = False,
    dry_run: bool = False,
) -> ScaffoldResult:
    """Scaffold `target` ("repo" → CLAUDE.md, "local" → CLAUDE.local.md) at `root`.

    Refuses to overwrite an existing file unless `force=True` — this is a
    creation command, not a silent-clobber one. `dry_run` returns the prompt
    without writing or running an agent, for a preview.
    """
    root = root.resolve()
    filename = filename_for(target)  # raises ValueError on an unknown target
    out = root / filename
    prompt = build_scaffold_prompt(str(root), target)

    if dry_run:
        return ScaffoldResult(ok=True, prompt=prompt)

    if out.exists() and not force:
        return ScaffoldResult(ok=False, error=f"{filename} already exists at {root} (use --force to overwrite)")

    agent = agent or AgentRunner()
    result = agent.run(prompt, cwd=root, role="claude-md-scaffold")
    text = (result.output or "").strip()
    used_fallback = not result.ok or not text
    if used_fallback:
        text = skeleton(root.name, target)

    write_artifact(out, text.strip() + "\n")
    return ScaffoldResult(ok=True, path=out, used_skeleton_fallback=used_fallback, prompt=prompt)
