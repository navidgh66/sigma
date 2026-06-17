"""Pipeline runner: drive commands/*.md stages and manage spec artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from cli.paths import sigma_home
from cli.runner import AgentResult, AgentRunner, write_artifact

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


# Each stage reads the prior stage's artifact as input context.
PRIOR_ARTIFACT: Dict[str, str] = {
    "propose": "research.md",
    "blueprint": "proposals.md",
    "spec": "architecture.md",
    "tasks": "spec.md",
    "implement-task": "tasks.md",
    "verify": "spec.md",
}


def prior_context(stage_name: str, workspace: Path) -> Optional[str]:
    """Read the upstream artifact this stage depends on, if present."""
    upstream = PRIOR_ARTIFACT.get(stage_name)
    if not upstream:
        return None
    path = workspace / upstream
    if path.exists():
        return path.read_text()
    return None


def render_invocation(stage: Stage, workspace: Path) -> str:
    """Produce the prompt to hand Claude Code for a stage.

    Embeds the command template, the upstream artifact (context chaining), and
    points it at the workspace. Built as a string so it is testable.
    """
    template = stage.template_path.read_text() if stage.exists else f"# /{stage.name}\n(template missing)"
    context = prior_context(stage.name, workspace)
    context_block = ""
    if context:
        upstream = PRIOR_ARTIFACT.get(stage.name)
        context_block = f"\n--- input: {upstream} ---\n{context}\n"
    return (
        f"Execute the sigma '{stage.name}' stage.\n"
        f"Workspace: {workspace}\n"
        f"Write artifact: {workspace / stage.artifact}\n"
        f"{context_block}\n"
        f"--- command template ---\n{template}\n"
    )


def execute_stage(
    stage_name: str,
    workspace: Path,
    agent: Optional[AgentRunner] = None,
    prompt_prefix: str = "",
) -> AgentResult:
    """Run a pipeline stage through the agent runner and persist its artifact.

    For file-artifact stages (research.md, spec.md, ...) the agent output is
    written to the artifact path. Directory artifacts (impl/, verify/) are left
    for the agent to populate; we still capture a run log.

    `prompt_prefix` lets a caller (e.g. Hermes) prepend skill context to the
    stage prompt without changing how the artifact is persisted.
    """
    stage = load_stage(stage_name)
    if stage is None:
        return AgentResult(ok=False, output="", error=f"unknown stage: {stage_name}")
    if not stage.exists:
        return AgentResult(ok=False, output="", error=f"template missing: {stage.template_path}")

    agent = agent or AgentRunner()
    prompt = render_invocation(stage, workspace)
    if prompt_prefix:
        prompt = f"{prompt_prefix}\n\n{prompt}"
    result = agent.run(prompt, cwd=workspace)

    if result.ok and result.output:
        if stage.artifact.endswith("/"):
            # Directory artifact: record a run log alongside the dir.
            workspace.joinpath(stage.artifact).mkdir(parents=True, exist_ok=True)
            write_artifact(workspace / f"{stage.name}.log.md", result.output)
        else:
            write_artifact(workspace / stage.artifact, result.output)
    return result
