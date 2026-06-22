"""Pipeline runner: drive commands/*.md stages and manage spec artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from cli.paths import sigma_home
from cli.runner import AgentResult, AgentRunner, write_artifact

# Machine manifest the weave step writes (see cli/weave.py). The verify stage
# reads it for full-chain review. Read directly (not via cli.weave_manifest) to
# avoid a circular import: weave_manifest imports STAGES from this module.
CHAIN_MANIFEST = "chain.json"

# Ordered pipeline. Each stage maps to a command template and an output artifact.
# `template` defaults to `name` (commands/<name>.md); the two grill GATE stages
# reuse the single commands/grill.md template (differing only by --target) and
# write a grill report. A grill gate is adversarial (maker ≠ griller) and BLOCKs
# the auto chain on a CRITICAL/HIGH logic flaw — see hermes.GRILL_GATE_STAGES.
STAGES: List[Dict[str, str]] = [
    {"name": "research", "artifact": "research.md"},
    {"name": "propose", "artifact": "proposals.md"},
    {"name": "blueprint", "artifact": "architecture.md"},
    {"name": "grill-blueprint", "artifact": "grill/blueprint.md", "template": "grill"},
    {"name": "spec", "artifact": "spec.md"},
    {"name": "grill-spec", "artifact": "grill/spec.md", "template": "grill"},
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
    """Resolve a stage by name, including its template path/existence.

    A stage's command template defaults to its name (commands/<name>.md); a
    `template` override lets several stages share one template (the grill gates
    both use commands/grill.md).
    """
    for s in STAGES:
        if s["name"] == name:
            tmpl = command_template(s.get("template", name))
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


# Each stage reads the prior stage's artifact as input context. The grill gates
# read the artifact they interrogate (the design, the spec).
PRIOR_ARTIFACT: Dict[str, str] = {
    "propose": "research.md",
    "blueprint": "proposals.md",
    "grill-blueprint": "architecture.md",
    "spec": "architecture.md",
    "grill-spec": "spec.md",
    "tasks": "spec.md",
    "implement-task": "tasks.md",
    "verify": "spec.md",
}

# The grill gate stages and the --target each one grills (single grill template).
GRILL_TARGET: Dict[str, str] = {
    "grill-blueprint": "blueprint",
    "grill-spec": "spec",
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


def chain_context(stage_name: str, workspace: Path) -> Optional[str]:
    """Full-chain review context for the verify stage, from chain.json.

    The verify stage reviews against the WHOLE artifact chain, not just its single
    upstream artifact. When a weave manifest (chain.json) is present, assemble a
    context block inlining every present FILE artifact in pipeline order. Returns
    None when the stage is not verify, the manifest is absent/unreadable, or no
    file artifacts exist — callers then fall back to `prior_context` (fail-safe:
    a missing derived artifact never blocks the pipeline).
    """
    if stage_name != "verify":
        return None
    manifest_path = workspace / CHAIN_MANIFEST
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None
    stages = manifest.get("stages") if isinstance(manifest, dict) else None
    if not isinstance(stages, list):
        return None

    blocks: List[str] = []
    for entry in stages:
        if not isinstance(entry, dict):
            continue
        if not entry.get("exists") or entry.get("is_dir"):
            continue
        artifact = entry.get("artifact")
        if not isinstance(artifact, str):
            continue
        path = workspace / artifact
        if not path.exists():
            continue
        cites = entry.get("citations")
        cite_note = f"  ({cites} citations)" if cites else ""
        blocks.append(f"[{entry.get('name')}] {artifact}{cite_note}\n{path.read_text()}")
    if not blocks:
        return None
    body = "\n\n".join(blocks)
    return f"\n--- artifact chain (review against ALL of these) ---\n{body}\n--- end chain ---\n"


def render_invocation(stage: Stage, workspace: Path) -> str:
    """Produce the prompt to hand Claude Code for a stage.

    Embeds the command template, context chaining, and points it at the
    workspace. Built as a string so it is testable. The verify stage prefers a
    full-chain context block (from chain.json) when available, falling back to
    its single upstream artifact.
    """
    template = stage.template_path.read_text() if stage.exists else f"# /{stage.name}\n(template missing)"
    context_block = ""
    chain = chain_context(stage.name, workspace)
    if chain:
        context_block = chain
    else:
        context = prior_context(stage.name, workspace)
        if context:
            upstream = PRIOR_ARTIFACT.get(stage.name)
            context_block = f"\n--- input: {upstream} ---\n{context}\n"
    # Grill gates share one template; tell it which artifact to interrogate.
    target = GRILL_TARGET.get(stage.name)
    target_block = f"--target {target}\n" if target else ""
    return (
        f"Execute the sigma '{stage.name}' stage.\n"
        f"{target_block}"
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
