"""Map pipeline stages to bundled (vendored) skills and inject them into prompts.

Pure logic: given a stage name and the vendored-skills directory, resolve which
SKILL.md bodies to prepend to a stage prompt. Hermes uses this to drive each
stage with the right skill, while the vendored skills also work standalone in
Claude Code. No subprocess, no I/O beyond reading the vendored markdown — fully
testable with a fake vendor tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from cli.paths import sigma_home

# Stage → vendored skill slugs. Slugs live under skills/vendor/.
# superpowers/<slug>/SKILL.md, or caveman/SKILL.md.
STAGE_SKILLS: Dict[str, List[str]] = {
    "propose": ["brainstorming"],
    "blueprint": ["brainstorming"],
    "spec": ["writing-plans"],
    "implement-task": ["test-driven-development"],
    "verify": ["systematic-debugging", "verification-before-completion"],
    # `loop` reuses the verify checkers when a cycle fails.
    "loop": ["systematic-debugging"],
    # Anti-slop cleanup pass (loop --simplify). Distinct agent, behaviour-preserving.
    "simplify": ["code-simplifier"],
}

# Slug used for terse/compressed output across every stage.
CAVEMAN_SLUG = "caveman"

# Slugs that live directly under skills/vendor/<slug>/ (not superpowers/).
_TOP_LEVEL = {CAVEMAN_SLUG, "code-simplifier"}


def vendor_dir() -> Path:
    """Default vendored-skills directory inside the sigma install."""
    return sigma_home() / "skills" / "vendor"


def skills_for_stage(stage: str) -> List[str]:
    """Return the vendored skill slugs mapped to a stage (empty if none)."""
    return list(STAGE_SKILLS.get(stage, []))


def _skill_file(slug: str, vendor: Path) -> Path:
    """Resolve the SKILL.md path for a slug within the vendor tree."""
    if slug in _TOP_LEVEL:
        return vendor / slug / "SKILL.md"
    return vendor / "superpowers" / slug / "SKILL.md"


def skill_paths(stage: str, vendor: Path) -> List[Path]:
    """Resolve existing SKILL.md paths for a stage. Missing files are skipped."""
    paths: List[Path] = []
    for slug in skills_for_stage(stage):
        f = _skill_file(slug, vendor)
        if f.exists():
            paths.append(f)
    return paths


def _read_skill(slug: str, vendor: Path) -> str:
    f = _skill_file(slug, vendor)
    if not f.exists():
        return ""
    return f.read_text()


def inject_skill(prompt: str, stage: str, vendor: Path, terse: bool = False) -> str:
    """Prepend the mapped skills' bodies to a stage prompt.

    Returns the prompt unchanged when no skill maps to the stage and `terse` is
    off. When `terse`, the caveman skill is appended so output is compressed.
    """
    blocks: List[str] = []
    for slug in skills_for_stage(stage):
        body = _read_skill(slug, vendor)
        if body:
            blocks.append(f"--- skill: {slug} ---\n{body}")

    if terse:
        caveman = _read_skill(CAVEMAN_SLUG, vendor)
        if caveman:
            blocks.append(f"--- skill: {CAVEMAN_SLUG} ---\n{caveman}")

    if not blocks:
        return prompt

    skill_context = "\n\n".join(blocks)
    return f"{skill_context}\n\n--- task ---\n{prompt}"
