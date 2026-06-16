"""Pipeline runner: drive commands/*.md stages and manage spec artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from cli.paths import sigma_home

# Ordered pipeline. Each stage maps to commands/<name>.md and an output artifact.
STAGES: List[Dict[str, str]] = [
    {"name": "research", "artifact": "research.md"},
    {"name": "propose", "artifact": "proposals.md"},
    {"name": "blueprint", "artifact": "architecture.md"},
    {"name": "spec", "artifact": "spec.md"},
    {"name": "tasks", "artifact": "tasks.md"},
    {"name": "implement-task", "artifact": "impl/"},
    {"name": "verify", "artifact": "verify/"},
    {"name": "loop", "artifact": "loop-log.md"},
]

STAGE_NAMES = [s["name"] for s in STAGES]


@dataclass
class Stage:
    name: str
    artifact: str
    template_path: Path
    exists: bool


def command_template(name: str) -> Path:
    """Path to a command template markdown file."""
    return sigma_home() / "commands" / f"{name}.md"


def load_stage(name: str) -> Optional[Stage]:
    """Resolve a stage by name, including its template path/existence."""
    for s in STAGES:
        if s["name"] == name:
            tmpl = command_template(name)
            return Stage(
                name=name,
                artifact=s["artifact"],
                template_path=tmpl,
                exists=tmpl.exists(),
            )
    return None


def next_stage(name: str) -> Optional[str]:
    """Return the stage that follows `name`, or None if last/unknown."""
    if name not in STAGE_NAMES:
        return None
    idx = STAGE_NAMES.index(name)
    if idx + 1 < len(STAGE_NAMES):
        return STAGE_NAMES[idx + 1]
    return None


def render_invocation(stage: Stage, workspace: Path) -> str:
    """Produce the prompt to hand Claude Code for a stage.

    Embeds the command template and points it at the workspace. The CLI passes
    this to `claude`; here we just build the string so it is testable.
    """
    template = stage.template_path.read_text() if stage.exists else f"# /{stage.name}\n(template missing)"
    return (
        f"Execute the sigma '{stage.name}' stage.\n"
        f"Workspace: {workspace}\n"
        f"Write artifact: {workspace / stage.artifact}\n\n"
        f"--- command template ---\n{template}\n"
    )
