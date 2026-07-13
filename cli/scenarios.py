"""Pure logic for extracting executable BDD scenarios out of spec.md.

`/spec` already writes acceptance criteria as `Scenario:/Given/When/Then`
blocks (see commands/spec.md). This module reads those blocks back out so
`/e2e`, `/implement-task`, and `sigma loop --e2e` can drive them live instead
of only reasoning about them. Mirrors `cli/eval.py`'s `parse_eval_set` shape:
regex-based markdown parsing into a dataclass, no subprocess, no clock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_SCENARIO_RE = re.compile(r"^\s*Scenario:\s*(?P<name>.+?)\s*$")
_GIVEN_RE = re.compile(r"^\s*Given\s+(?P<val>.+?)\s*$", re.IGNORECASE)
_WHEN_RE = re.compile(r"^\s*When\s+(?P<val>.+?)\s*$", re.IGNORECASE)
_THEN_RE = re.compile(r"^\s*Then\s+(?P<val>.+?)\s*$", re.IGNORECASE)


@dataclass
class Scenario:
    name: str
    given: str
    when: str
    then: str


def parse_scenarios(spec_md: str) -> List[Scenario]:
    """Extract every Scenario:/Given/When/Then block from spec.md text.

    Lenient: a Scenario header with a missing Given/When/Then line just leaves
    that field empty rather than dropping the whole block — a partially
    written scenario is still worth surfacing to a human/agent.
    """
    scenarios: List[Scenario] = []
    cur: Optional[dict] = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            scenarios.append(
                Scenario(
                    name=cur["name"],
                    given=cur.get("given", ""),
                    when=cur.get("when", ""),
                    then=cur.get("then", ""),
                )
            )
        cur = None

    for line in spec_md.splitlines():
        header = _SCENARIO_RE.match(line)
        if header:
            flush()
            cur = {"name": header.group("name").strip()}
            continue
        if cur is None:
            continue
        given = _GIVEN_RE.match(line)
        when = _WHEN_RE.match(line)
        then = _THEN_RE.match(line)
        if given:
            cur["given"] = given.group("val")
        elif when:
            cur["when"] = when.group("val")
        elif then:
            cur["then"] = then.group("val")
    flush()
    return scenarios


def find_scenario(scenarios: List[Scenario], name: str) -> Optional[Scenario]:
    """Case-insensitive exact match on scenario name."""
    target = name.strip().lower()
    for s in scenarios:
        if s.name.strip().lower() == target:
            return s
    return None


def _case_slug(name: str) -> str:
    """Slugify a scenario name into an eval-case id (same shape as loop slugs)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "scenario"


def render_eval_set(topic: str, scenarios: List[Scenario]) -> str:
    """Render spec.md's BDD scenarios as a sigma eval set (spec→eval bridge).

    Each Scenario becomes one `## case:` block that `eval.parse_eval_set`
    reads back verbatim: the Given/When framing is the case input, the Then
    assertion is the rubric. The eval set is DERIVED — spec.md stays the
    source of truth; regenerate after editing the spec (the header says so).
    Deterministic: same scenarios → same text (no clock).
    """
    lines: List[str] = [
        f"# Eval set: {topic}",
        "",
        "Generated from spec.md's Scenario/Given/When/Then blocks — do not edit",
        "by hand; edit the spec and regenerate with `sigma eval --from-spec`.",
        "",
    ]
    for sc in scenarios:
        lines.append(f"## case: {_case_slug(sc.name)}")
        lines.append(f"input: Given {sc.given}. When {sc.when} — describe what happens and whether the expected behavior holds.")
        lines.append(f"rubric: the outcome must satisfy: Then {sc.then}")
        lines.append("")
    return "\n".join(lines)
