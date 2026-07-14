# Spec — implementer axis token-economy report (`sigma trajectory --economy`)

**Source design:** `docs/superpowers/specs/2026-07-14-axis-economy-design.md`
**Domain:** ai-agent-engineering
**Status:** implementation-ready

## Summary

Add a deterministic, role-level token-economy report over an existing
`trajectory.jsonl`. It joins **tokens spent per loop axis** (implementer, verifier,
logic, advisor, e2e, simplifier, test-writer) with **whether that axis produced value
this run** (derived from `CycleOutcome` effect flags), ranks axes by
tokens-per-value-event, and surfaces idle-but-expensive axes as prune candidates. Pure
projection — no new agent, no extra tokens spent to measure.

## Requirements

### R1 — Effect flags on the cycle trajectory step
`cli/loop.py` `record_cycle_steps` MUST emit, on each `role="cycle"` step, the per-axis
effect flags already present on the `CycleOutcome`: `logic_ok`, `advised`, `e2e_ok`,
`simplified`, `test_written` (each `Optional[bool]`). Existing fields (`ok`, `domain`,
`lessons`) are unchanged.

### R2 — TrajectoryStep carries the effect flags
`cli/trajectory.py` `TrajectoryStep` gains the five optional bool fields. `build_step`
parses them leniently: absent → `None`; a non-bool value → `None` (never raises). A
trajectory written before this change (no effect fields) still reads.

### R3 — New pure module `cli/axis_economy.py`
- `AxisRow` dataclass: `role: str`, `token_total: Optional[int]`, `runs: int`,
  `value_events: int`, `is_core: bool`, `measured: bool`, `roi: Optional[float]`,
  `flag: Optional[str]`.
- `AxisEconomy` dataclass: `rows: List[AxisRow]`, `total_measured_tokens: int`,
  `cycles: int`, with `.render() -> str`.
- `build_economy(steps: List[TrajectoryStep]) -> AxisEconomy`: pure, deterministic.
  - Non-cycle steps → per-role token total (sum of the four token dims, real telemetry
    only) + run count.
  - `role="cycle"` steps → per-axis value tallies via the value model below.
  - `roi = token_total / max(value_events, 1)` for non-core measured axes; `None` when
    unmeasured or core.
  - `is_core` True for `implementer`/`verifier` (never flagged as prune candidates).
  - `measured` False when the role has no measured tokens across its steps.

### R4 — Value model
An axis's `value_events` count across the run's cycle steps:

| axis (role)  | value event                              | core? |
|--------------|------------------------------------------|-------|
| implementer  | every cycle                              | yes   |
| verifier     | every cycle                              | yes   |
| logic        | `logic_ok is False` (caught a fail)      | no    |
| advisor      | `advised is True` (rescued)              | no    |
| e2e          | `e2e_ok is False` (caught a live fail)   | no    |
| simplifier   | `simplified is True` (cleanup stuck)     | no    |
| test-writer  | `test_written is True`                   | no    |

### R5 — Flagging (surface-only, prune law)
An axis is flagged `flag = "prune candidate: 0 value events in this run"` only when
ALL hold, checked in this order (short-circuit so `None` is never compared):
`is_core is False` AND `measured is True` AND `token_total > 0` AND `value_events == 0`.
The `measured is True` check MUST precede the `token_total > 0` comparison, because an
unmeasured axis has `token_total = None` and `None > 0` raises `TypeError` in Python 3.
An axis with zero tokens AND zero value events is NOT flagged (no evidence — prune's
never-act-on-absent-evidence law). Core axes are never flagged.

### R6 — Honesty (no estimation)
Unmeasured axes (`measured is False`) are shown in the report labeled "unmeasured" and
excluded from ROI ranking — never assigned an estimated token count. Run-scoped wording
("0 value events in this run"), never "useless".

### R7 — CLI surface
`sigma trajectory --economy` prints the economy report (a flag on the existing
`trajectory` command, mirroring `--efficiency`). `--json` composes with `--economy`
(emits the `AxisEconomy` as JSON via `dataclasses.asdict`). Same topic resolution and
`read_steps(ws)` input as the sibling flags. Missing workspace → exit 1 (existing
behavior); otherwise exit 0.

### R8 — Fail-safe
Empty/missing trajectory → a "No trajectory data yet" line, never a crash. Division
guarded (`max(value_events, 1)`). `build_economy`/`render` never raise on any input.

## Acceptance criteria (BDD)

Scenario: economy report flags an idle expensive axis
Given a trajectory with logic-role steps totaling real measured tokens and cycle steps where logic_ok was never False
When I run sigma trajectory --economy for that workspace
Then the report lists the logic axis as a prune candidate with its token total and zero value events

Scenario: economy report credits a productive axis
Given a trajectory where the advisor role spent tokens and at least one cycle step has advised true
When I run sigma trajectory --economy for that workspace
Then the report shows the advisor axis as earning its tokens and does not flag it as a prune candidate

Scenario: core axes are never flagged
Given a trajectory with implementer and verifier steps and several cycle steps
When I run sigma trajectory --economy for that workspace
Then neither the implementer nor the verifier axis is listed as a prune candidate

Scenario: unmeasured axis is not estimated
Given a trajectory whose logic cycle steps exist but no logic step carries token telemetry
When I run sigma trajectory --economy for that workspace
Then the logic axis is shown as unmeasured and is excluded from the ROI ranking with no invented token number

Scenario: empty trajectory is safe
Given a workspace whose trajectory.jsonl is absent or empty
When I run sigma trajectory --economy for that workspace
Then the command prints a no-data-yet message and exits zero without raising

Scenario: old trajectory without effect fields still reads
Given a trajectory.jsonl written before the effect fields existed
When I run sigma trajectory --economy for that workspace
Then every axis value tally degrades to zero or unmeasured and the command does not raise a KeyError

Scenario: JSON output composes with economy
Given a trajectory with a mix of measured and cycle steps
When I run sigma trajectory --economy --json for that workspace
Then the command emits the AxisEconomy as a single JSON object with rows, total_measured_tokens, and cycles

## Out of scope
Per-cycle attribution, LM-judged value, auto-disable, cross-run trend, and the Stage-3
optimizations themselves (this spec only builds the evidence instrument).

## Test plan
Pure unit tests in `tests/test_axis_economy.py` covering each BDD scenario against
hand-built `TrajectoryStep` lists (no agents). A `record_cycle_steps` test in the loop
suite asserting the effect flags reach the emitted step. Whole suite (924) stays green.
E2E: run `sigma trajectory --economy` against a real workspace (synthetic
trajectory.jsonl) and confirm the rendered report + `--json` shape + exit 0.
