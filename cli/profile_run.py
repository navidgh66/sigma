"""`sigma profile` — walk a codebase, emit its logic-invariant profile.

Drives the AgentRunner (the single execution chokepoint) to produce
`sigma/profile/logic-profile.md`: a living record of the codebase's ML-logic and
system-logic invariants that `review` reads as grounding. Refreshed manually
(freshness is staleness-flagged, not auto).

Prompt building, output handling, and validation are pure/injectable (in
`cli/profile_manifest.py`) so the flow is testable without a real agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from cli.profile_manifest import (
    ML_LOGIC_HEADER,
    SYSTEM_LOGIC_HEADER,
    profile_path,
    profile_skeleton,
    validate_profile,
)
from cli.runner import AgentRunner, write_artifact

PROFILE_INSTRUCTIONS = """Walk this codebase and produce its LOGIC PROFILE — a
living record of the invariants a reviewer must protect. Read the project under:
{root}

Emit a single Markdown document, nothing before or after, with EXACTLY these two
sections (keep these headers verbatim):

{ml_header}
<The ML-logic invariants of THIS repo. Name real files. Cover: how data is split
(group/time/stratified) and the leakage guards; the metrics and losses and why;
reward shaping / clipping (if RL); eval determinism (seeds); train/serve
consistency. State each as an invariant a change must not silently break.>

{sys_header}
<The system-logic invariants of THIS repo. Name real files. Cover: control-flow
contracts (what must terminate, ordering guarantees); data contracts / schemas;
concurrency and shared-state rules; API / interface boundaries and compatibility;
failure-handling expectations. State each as an invariant a change must not break.>

Be concrete and specific — every invariant should point at real code. Prefer a
short, true list over a long, speculative one.
"""


@dataclass
class ProfileResult:
    ok: bool
    profile_path: Optional[Path] = None
    problems: List[str] = field(default_factory=list)
    error: Optional[str] = None
    prompt: str = ""


def build_profile_prompt(root: Path) -> str:
    """Build the profile-walk prompt (headers must match the manifest contract)."""
    return PROFILE_INSTRUCTIONS.format(
        root=root, ml_header=ML_LOGIC_HEADER, sys_header=SYSTEM_LOGIC_HEADER
    )


def run_profile(
    root: Path,
    project_name: str = "",
    agent: Optional[AgentRunner] = None,
    dry_run: bool = False,
) -> ProfileResult:
    """Drive the agent to profile `root`, then write + validate the artifact.

    On a missing-both-sections reply, falls back to writing the skeleton so the
    operator gets a fillable file rather than nothing (fail-safe). Validation
    problems are surfaced, never fatal.
    """
    root = root.resolve()
    prompt = build_profile_prompt(root)
    if dry_run:
        return ProfileResult(ok=True, prompt=prompt)

    agent = agent or AgentRunner()
    result = agent.run(prompt, cwd=root)
    if not result.ok:
        return ProfileResult(ok=False, error=result.error or "agent run failed", prompt=prompt)

    text = result.output.strip()
    problems = validate_profile(text)
    if ML_LOGIC_HEADER not in text and SYSTEM_LOGIC_HEADER not in text:
        # Agent produced neither section — write the skeleton instead of garbage.
        text = profile_skeleton(project_name or root.name)
        problems = ["agent produced no recognizable sections; wrote skeleton instead"]

    out = profile_path(root)
    write_artifact(out, text + "\n")
    return ProfileResult(ok=True, profile_path=out, problems=problems, prompt=prompt)
