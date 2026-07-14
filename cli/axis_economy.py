"""Pure logic for the loop's per-axis token-economy report (`sigma trajectory --economy`).

`sigma loop --execute` fans out up to 8 distinct agents per task cycle (test-writer,
implementer, verifier, logic, e2e, advisor, simplifier, regression), each a fresh
`claude -p` subprocess. `trajectory.efficiency_report` already reports the run's TOTAL
measured tokens; this module goes finer: it joins tokens-spent-PER-AXIS with
did-that-axis-produce-value-this-run, so an axis that burns real tokens every cycle
while never once changing an outcome (e.g. a logic evaluator that never flips a verify
PASS to FAIL) is surfaced as a prune candidate.

Two data projections over one source (`trajectory.jsonl`, already written per run):
  - non-cycle steps (role=implementer/verifier/logic/…) → tokens + run count per role
    (REAL telemetry only — a role with no measured tokens is "unmeasured", NEVER
    estimated; that guess lives in `sigma cost`);
  - role="cycle" steps → per-axis value tallies via the value model below (the effect
    flags `record_cycle_steps` stamps from each CycleOutcome).

Laws (sigma-wide, mirrored here):
  - pure: no clock, no subprocess, no file I/O — folds a list of TrajectoryStep;
  - fail-safe: any input (empty, old-format, garbage-degraded) renders/returns without
    raising — a report tool must never break a session;
  - prune law: SURFACE an idle axis, never auto-disable it (the human reads it, then
    adds `--no-logic` etc.); never act on absent evidence (zero tokens AND zero value →
    not flagged).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from cli.trajectory import TrajectoryStep

CYCLE_ROLE = "cycle"

# Core axes always run and always earn (implementer builds, verifier gates) — they are
# never flagged as prune candidates. Every other axis is optional and must justify its
# tokens via a value event.
_CORE_ROLES = ("implementer", "verifier")

# Maps an optional axis's role name → the CycleOutcome effect field + the predicate that
# counts as a "value event" for it (see spec R4). A value event means the axis changed
# the run's outcome this cycle: the logic/e2e axes EARN by CATCHING a failure the code
# checker missed (flag is False), the advisor/simplifier/test-writer by SUCCEEDING
# (flag is True).
_VALUE_FIELD = {
    "logic": ("logic_ok", False),       # caught a fail verify passed
    "e2e": ("e2e_ok", False),           # caught a live behavioral fail
    "advisor": ("advised", True),       # rescued a failing cycle
    "simplifier": ("simplified", True), # cleanup stuck past re-verify
    "test-writer": ("test_written", True),
}

_TOKEN_DIMS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


@dataclass
class AxisRow:
    role: str
    token_total: Optional[int]  # None when unmeasured (no telemetry on any of its steps)
    runs: int
    value_events: int
    is_core: bool
    measured: bool
    roi: Optional[float] = None  # tokens per value event; None when unmeasured or core
    flag: Optional[str] = None   # set only for a surfaced prune candidate


@dataclass
class AxisEconomy:
    rows: List[AxisRow] = field(default_factory=list)
    total_measured_tokens: int = 0
    cycles: int = 0

    def _candidates(self) -> List[AxisRow]:
        """Flagged prune candidates, worst ROI (most tokens per value event) first."""
        flagged = [r for r in self.rows if r.flag]
        return sorted(flagged, key=lambda r: r.roi or 0.0, reverse=True)

    def _earning(self) -> List[AxisRow]:
        """Non-candidate rows that actually ran, most tokens first."""
        rows = [r for r in self.rows if not r.flag and r.runs > 0]
        return sorted(rows, key=lambda r: (r.token_total or 0), reverse=True)

    def render(self) -> str:
        if not self.rows:
            return (
                "# sigma axis economy\n\nNo trajectory data yet. "
                "Run `sigma loop --execute` first."
            )
        lines = [
            "# sigma axis economy",
            "",
            f"**{self.cycles} cycle(s)**, {self.total_measured_tokens:,} measured tokens "
            "across all axes (REAL usage from `claude --output-format json` — unmeasured "
            "axes are excluded, never estimated).",
            "",
        ]

        candidates = self._candidates()
        lines += ["## Review — idle this run", ""]
        if candidates:
            lines.append(
                "These optional axes spent tokens but produced no value event this run. "
                "Consider disabling them for similar work (e.g. `--no-logic`) — surfaced, "
                "not auto-disabled; a run where nothing failed does not prove an axis useless."
            )
            lines.append("")
            for r in candidates:
                lines.append(
                    f"- **{r.role}**: ~{r.token_total:,} tokens over {r.runs} run(s), "
                    f"0 value events in this run → {r.flag}"
                )
        else:
            lines.append("No idle-but-expensive axes this run.")
        lines.append("")

        lines += ["## Earning", ""]
        earning = self._earning()
        if earning:
            for r in earning:
                if not r.measured:
                    lines.append(
                        f"- **{r.role}**{' (core)' if r.is_core else ''}: {r.runs} run(s), "
                        "tokens unmeasured (no telemetry) — excluded from ROI ranking."
                    )
                else:
                    roi = f", ~{r.roi:,.0f} tokens/value event" if r.roi is not None else ""
                    core = " (core — always earns)" if r.is_core else ""
                    lines.append(
                        f"- **{r.role}**{core}: ~{r.token_total:,} tokens over {r.runs} "
                        f"run(s), {r.value_events} value event(s){roi}"
                    )
        else:
            lines.append("No axis steps recorded yet.")
        lines.append("")
        return "\n".join(lines)


def _step_tokens(step: "TrajectoryStep") -> Optional[int]:
    """Sum a step's measured token dims. None when the step carries no telemetry at all.

    A step is "measured" only if at least one dim is a real number; a step with every
    dim None (pre-telemetry, codex, parse failure) contributes None — never a fake 0
    that would make an unmeasured axis look cheap.
    """
    total = 0
    seen = False
    for dim in _TOKEN_DIMS:
        v = getattr(step, dim, None)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += int(v)
            seen = True
    return total if seen else None


def build_economy(steps: List["TrajectoryStep"]) -> AxisEconomy:
    """Fold trajectory steps into a per-axis economy (pure, deterministic).

    Non-cycle steps give tokens + run count per role; role="cycle" steps give the
    per-axis value tallies. Fail-safe on any input (empty → empty economy).
    """
    if not steps:
        return AxisEconomy()

    # Token + run aggregation over the real agent steps (everything but the synthetic
    # cycle markers). measured tokens accumulate only from steps that actually carry
    # telemetry; a role seen only via unmeasured steps stays token_total=None.
    tokens_by_role: Dict[str, int] = {}
    measured_roles = set()
    runs_by_role: Dict[str, int] = {}
    for step in steps:
        if step.role == CYCLE_ROLE:
            continue
        runs_by_role[step.role] = runs_by_role.get(step.role, 0) + 1
        tok = _step_tokens(step)
        if tok is not None:
            tokens_by_role[step.role] = tokens_by_role.get(step.role, 0) + tok
            measured_roles.add(step.role)

    # Value tallies over the cycle markers.
    cycle_steps = [s for s in steps if s.role == CYCLE_ROLE]
    cycles = len(cycle_steps)
    value_by_role: Dict[str, int] = {}
    for role, (field_name, want) in _VALUE_FIELD.items():
        value_by_role[role] = sum(
            1 for s in cycle_steps if getattr(s, field_name, None) is want
        )
    # Core axes earn on every cycle by definition.
    for core in _CORE_ROLES:
        value_by_role[core] = cycles

    # A role appears in the report if it ran (has non-cycle steps) OR has a value model
    # entry (so a configured-but-not-yet-run axis is still nameable). Union both.
    roles = set(runs_by_role) | set(_CORE_ROLES) | set(_VALUE_FIELD)
    rows: List[AxisRow] = []
    for role in sorted(roles):
        runs = runs_by_role.get(role, 0)
        measured = role in measured_roles
        token_total: Optional[int] = tokens_by_role.get(role) if measured else None
        value_events = value_by_role.get(role, 0)
        is_core = role in _CORE_ROLES
        roi: Optional[float] = None
        if measured and not is_core and token_total is not None:
            roi = token_total / max(value_events, 1)
        row = AxisRow(
            role=role,
            token_total=token_total,
            runs=runs,
            value_events=value_events,
            is_core=is_core,
            measured=measured,
            roi=roi,
        )
        # Flag order matters (spec R5): measured MUST be checked before token_total > 0,
        # because an unmeasured axis has token_total=None and None > 0 raises TypeError.
        if (
            not is_core
            and measured
            and token_total is not None
            and token_total > 0
            and value_events == 0
        ):
            row.flag = "prune candidate: 0 value events in this run"
        rows.append(row)

    total_measured = sum(tokens_by_role.values())
    return AxisEconomy(rows=rows, total_measured_tokens=total_measured, cycles=cycles)
