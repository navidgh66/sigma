"""Pure index over the domain context-engines.

The 9 domain context-engines (`context-engines/<domain>/`) are sigma's crown
jewel: hand-authored implementer guidance, verifier checks, and a logic-evaluator
per domain. This module resolves a domain to its on-disk files and verifies they
exist, so the `skills/sigma-domains` skill can route a task to the right files and
a test catches a missing/renamed context-engine rather than silently skipping it.

Pure and side-effect free: it only reads the filesystem layout (never spawns an
agent, never mutates state). The skill INDEXES these files — it does not duplicate
their content, so `context-engines/` stays the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from cli.paths import DOMAINS, sigma_home

# The logic-evaluator lives under verifiers/ in every domain (the third,
# reasoning-grading axis distinct from code-quality verifiers).
LOGIC_EVALUATOR = "logic-evaluator.md"


@dataclass
class DomainContext:
    """Resolved context-engine layout for one domain."""

    domain: str
    root: Path
    implementers: List[str] = field(default_factory=list)
    verifiers: List[str] = field(default_factory=list)
    has_logic_evaluator: bool = False

    @property
    def exists(self) -> bool:
        return self.root.is_dir()


def context_engines_dir(home: Optional[Path] = None) -> Path:
    """Directory holding all domain context-engines."""
    return (home or sigma_home()) / "context-engines"


def _list_md(directory: Path) -> List[str]:
    """Sorted markdown filenames in a directory (empty if absent)."""
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.suffix == ".md" and p.is_file())


def resolve_domain(domain: str, home: Optional[Path] = None) -> DomainContext:
    """Resolve one domain to its implementer/verifier files + logic-evaluator."""
    root = context_engines_dir(home) / domain
    verifiers = _list_md(root / "verifiers")
    return DomainContext(
        domain=domain,
        root=root,
        implementers=_list_md(root / "implementers"),
        verifiers=verifiers,
        has_logic_evaluator=LOGIC_EVALUATOR in verifiers,
    )


def resolve_all(home: Optional[Path] = None) -> List[DomainContext]:
    """Resolve every known domain (from paths.DOMAINS)."""
    return [resolve_domain(d, home=home) for d in DOMAINS]


def validate_domains(home: Optional[Path] = None) -> List[str]:
    """Check every domain has implementers, verifiers, and a logic-evaluator.

    Returns a list of problems (empty == all domains well-formed). This is the
    guard that catches a missing/renamed context-engine file.
    """
    problems: List[str] = []
    for ctx in resolve_all(home):
        if not ctx.exists:
            problems.append(f"{ctx.domain}: missing context-engine dir {ctx.root}")
            continue
        if not ctx.implementers:
            problems.append(f"{ctx.domain}: no implementer files in implementers/")
        if not ctx.verifiers:
            problems.append(f"{ctx.domain}: no verifier files in verifiers/")
        if not ctx.has_logic_evaluator:
            problems.append(f"{ctx.domain}: missing verifiers/{LOGIC_EVALUATOR}")
    return problems
