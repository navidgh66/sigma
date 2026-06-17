"""Hybrid routing for Hermes: state-driven by default, intent override on demand.

Default routing is deterministic and free: inspect which artifacts exist in the
spec workspace and infer the next pipeline stage. Only when the user's message
signals a jump ("redo research", "skip to verify") do we spend one model call to
classify intent. Classification is parsed skeptically and falls back to the
state-driven stage when it yields nothing valid.

Pure except for the injected runner, so it is fully testable with a fake.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from cli.paths import DOMAINS
from cli.pipeline import STAGE_NAMES, STAGES

# Words that signal the user wants to override the natural next stage.
_OVERRIDE_PATTERNS = (
    r"\bredo\b",
    r"\bre-?run\b",
    r"\bskip\b",
    r"\bgo back\b",
    r"\bjump\b",
    r"\bstart over\b",
    r"\brestart\b",
    r"\bagain\b",
)
_OVERRIDE_RE = re.compile("|".join(_OVERRIDE_PATTERNS), re.IGNORECASE)

# A stage name appearing explicitly in the message is also an override signal.
_STAGE_MENTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in STAGE_NAMES) + r")\b", re.IGNORECASE
)


@dataclass
class Route:
    stage: Optional[str]
    domain: Optional[str]
    reason: str


def scan_state(workspace: Path) -> str:
    """Infer the next stage from which artifacts already exist.

    Returns the first stage whose artifact is missing. Directory artifacts
    (impl/, verify/) count as present once the directory exists.
    """
    for stage in STAGES:
        name = stage["name"]
        artifact = stage["artifact"]
        path = workspace / artifact.rstrip("/")
        if not path.exists():
            return name
    # Everything present → loop is the terminal stage.
    return STAGE_NAMES[-1]


def needs_override(message: str) -> bool:
    """True when the message signals a jump away from the natural next stage."""
    if not message:
        return False
    if _OVERRIDE_RE.search(message):
        return True
    return bool(_STAGE_MENTION_RE.search(message))


_CLASSIFY_PROMPT = (
    "You are a router for the sigma pipeline. Stages: "
    + ", ".join(STAGE_NAMES)
    + ". Domains: "
    + ", ".join(DOMAINS)
    + ".\nGiven the user's request, choose the single stage to run next and the "
    "domain it belongs to. Reply with exactly two lines:\n"
    "STAGE: <stage>\nDOMAIN: <domain>\n\nRequest: {message}"
)


def _parse_classification(text: str) -> Route:
    stage: Optional[str] = None
    domain: Optional[str] = None
    for line in text.splitlines():
        s = line.strip()
        upper = s.upper()
        if upper.startswith("STAGE:"):
            cand = s.split(":", 1)[1].strip().lower()
            if cand in STAGE_NAMES:
                stage = cand
        elif upper.startswith("DOMAIN:"):
            cand = s.split(":", 1)[1].strip().lower()
            if cand in DOMAINS:
                domain = cand
    return Route(stage=stage, domain=domain, reason="intent-classified")


def classify(message: str, runner) -> Route:
    """Spend one model call to classify the user's intent into a stage+domain."""
    result = runner.run(_CLASSIFY_PROMPT.format(message=message))
    if not result.ok or not result.output:
        return Route(stage=None, domain=None, reason="classify-failed")
    return _parse_classification(result.output)


def route(message: str, workspace: Path, runner) -> Route:
    """Resolve the next (stage, domain) for a Hermes message.

    State-driven by default (zero model cost). When the message signals a jump,
    classify intent with one model call; if that yields no valid stage, fall back
    to the state-driven stage.
    """
    state_stage = scan_state(workspace)
    if not needs_override(message):
        return Route(stage=state_stage, domain=None, reason="state-driven next stage")

    classified = classify(message, runner)
    if classified.stage is None:
        return Route(
            stage=state_stage,
            domain=classified.domain,
            reason="override unparseable → state fallback",
        )
    return classified


def available_stages() -> List[str]:
    """Expose the ordered stage names (convenience for callers/tests)."""
    return list(STAGE_NAMES)
