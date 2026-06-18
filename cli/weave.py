"""`sigma weave` — weave the pipeline's stage artifacts into one HTML chain.

Hybrid design (see docs/superpowers/specs/2026-06-18-html-artifact-chain-design.md):
markdown stays the engine's source of truth; this produces two DERIVED outputs in
the spec workspace:

  - chain.json  — pure, deterministic machine manifest (cli/weave_manifest)
  - chain.html  — a single self-contained, human-facing woven view, emitted by the
                  AgentRunner (mirrors cli/learn)

The manifest is written FIRST and never depends on the agent: even if the agent
run fails, chain.json is still produced. The agent's HTML is validated by the pure
`validate_chain_html` guard; problems are surfaced, not swallowed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from cli.pipeline import CHAIN_MANIFEST
from cli.runner import AgentRunner, write_artifact
from cli.weave_manifest import (
    build_manifest,
    present_file_stages,
    validate_chain_html,
)

CHAIN_HTML = "chain.html"
# Single source for the manifest filename: pipeline.py reads it for the verify
# full-chain context, so it owns the constant; weave writes the same file.
CHAIN_JSON = CHAIN_MANIFEST

WEAVE_INSTRUCTIONS = """Weave these sigma pipeline artifacts into ONE self-contained HTML page.

Topic: {topic}
Workspace: {workspace}

Produce a single, polished, self-contained HTML document (the "artifact chain"):
one navigable section per pipeline stage below, in order, cross-linked from a top
table of contents. Render each stage's markdown faithfully. For research, carry
through citations and keep any fact-vs-inference labelling. Add a provenance
footer noting the topic, which stages are present, and that this view is DERIVED
from the markdown artifacts (not the source of truth).

Design: one intentional editorial direction, clear scale-contrast hierarchy,
intentional spacing. Do NOT emit a generic uniform card grid or a stock gradient
hero. Include a `prefers-reduced-motion: reduce` block and animate only
compositor-friendly properties. CDN links are fine.

Output ONLY the HTML document — start with <!DOCTYPE html>, no commentary, no code
fence.

--- stage artifacts ---
{artifacts}
--- end stage artifacts ---
"""


@dataclass
class WeaveResult:
    ok: bool
    manifest_path: Optional[Path] = None
    html_path: Optional[Path] = None
    html_problems: List[str] = field(default_factory=list)
    error: Optional[str] = None
    prompt: str = ""


def _artifacts_block(workspace: Path, manifest: dict) -> str:
    """Inline each present file-artifact stage's markdown for the agent prompt."""
    blocks: List[str] = []
    for s in present_file_stages(manifest):
        path = workspace / str(s["artifact"])
        blocks.append(f"[{s['name']}] {s['artifact']}\n{path.read_text()}")
    return "\n\n".join(blocks)


def build_weave_prompt(
    workspace: Path, topic: str, manifest: Optional[dict] = None
) -> str:
    """Build the weave prompt embedding all present stage artifacts.

    Accepts a pre-built manifest so a caller (run_weave) can build it ONCE and
    keep the prompt and chain.json describing the same workspace snapshot.
    """
    manifest = manifest if manifest is not None else build_manifest(workspace)
    return WEAVE_INSTRUCTIONS.format(
        topic=topic or "(untitled)",
        workspace=workspace,
        artifacts=_artifacts_block(workspace, manifest) or "(no stage artifacts yet)",
    )


def _strip_fence(text: str) -> str:
    """Remove a surrounding ```html ... ``` fence if the agent added one."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Drop trailing blank lines, then a closing fence if present (agents
        # sometimes emit a newline after the closing ```).
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def run_weave(
    workspace: Path,
    topic: str = "",
    slug: str = "",
    agent: Optional[AgentRunner] = None,
    dry_run: bool = False,
) -> WeaveResult:
    """Write chain.json (always) and chain.html (agent), validating the HTML.

    The manifest is independent of the agent: it is written even when the agent
    run fails, so the machine contract always exists. `dry_run` prints the prompt
    and writes nothing.
    """
    # Build the manifest ONCE so the prompt and chain.json describe the same
    # workspace snapshot. In dry-run we still need it to populate the prompt.
    manifest = build_manifest(workspace, topic=topic, slug=slug)
    prompt = build_weave_prompt(workspace, topic, manifest=manifest)
    if dry_run:
        return WeaveResult(ok=True, prompt=prompt)

    workspace.mkdir(parents=True, exist_ok=True)

    # 1) Manifest first — pure, deterministic, never depends on the agent.
    manifest_path = write_artifact(
        workspace / CHAIN_JSON, json.dumps(manifest, indent=2) + "\n"
    )

    # 2) HTML via the agent.
    agent = agent or AgentRunner()
    result = agent.run(prompt, cwd=workspace)
    html = _strip_fence(result.output) if result.ok else ""
    if not result.ok or not html.strip():
        # Empty / fence-only output reduces to "" after stripping — never write a
        # corrupt chain.html, and report failure rather than a false success.
        return WeaveResult(
            ok=False,
            manifest_path=manifest_path,
            error=result.error or "agent produced no HTML",
            prompt=prompt,
        )

    expected = [s["name"] for s in present_file_stages(manifest)]
    problems = validate_chain_html(html, expected)
    html_path = write_artifact(workspace / CHAIN_HTML, html)

    return WeaveResult(
        ok=True,
        manifest_path=manifest_path,
        html_path=html_path,
        html_problems=problems,
        prompt=prompt,
    )
