# Design — implementer axis token-economy evaluation

**Date:** 2026-07-14
**Status:** design (approved section-by-section in brainstorming)
**Scope:** Stage 2 of a 3-stage arc (analysis → measurement tool → optimization).

## Problem

`sigma loop --execute` drives up to **8 distinct agents per task cycle** (test-writer,
implementer, verifier, logic, e2e, advisor×rounds, simplifier, regression), each a
fresh amnesiac `claude -p` subprocess (maker ≠ checker enforced by distinct
instances). Default (`--logic --simplify --advisor --e2e` all ON) = 5–6 agent runs
per PASSing task, more on FAIL.

sigma already *observes* cost:
- `cli/telemetry.py` parses real token/cost from `claude --output-format json` envelopes;
- `cli/trajectory.py` records one step per agent run (role, tokens, cost, duration);
- `cli/cost.py` estimates/routes/records a calibrated ledger;
- `trajectory.efficiency_report` reports cycle pass rate + escalation rate + total measured tokens.

**Gap:** nothing joins *tokens by axis* with *did that axis earn them*. A logic axis
that runs every cycle and never once flips a verify PASS to FAIL is pure token burn,
but no report surfaces it. The raw data exists on disk — it's just never joined.

## Findings (Stage-1 analysis, ← grounds this design)

1. **Amnesiac fan-out is the dominant cost.** No context is shared between axis
   subprocesses; each re-derives context from `cwd`. Only the advisor gets
   `impl_output` inlined.
2. **Duplicated prefix.** `_with_recall` (arch map + recalled lessons) prepends to
   implement AND verify; `_scenario_context` (BDD) appends to verify + logic + e2e.
   Same bytes re-sent per axis, not cached across subprocesses.
3. **Simplifier always pays a full re-verify** (`loop.py` `_run_simplify`) even when
   it returns "NO CHANGES NEEDED" — 1 wasted verify per already-clean PASS. On by default.
4. **No per-axis ROI signal** — the subject of this spec.

(Stage 3 acts on 2 + 3; this spec builds the instrument that proves they're worth it.)

## Goal

A deterministic, **role-level**, zero-extra-token report that ranks each loop axis by
**tokens-per-value-event** and flags "high tokens / zero value in this run" axes as
**surface-only** prune candidates (human reads it, then adds `--no-logic` etc. — never
auto-disabled). Pure projection over data already on disk. No new agent, no LM judge.

## Value model (deterministic, from existing `CycleOutcome` fields)

An axis is *productive* (earned its tokens this run) or *idle* (burned tokens, changed
nothing). Per axis, tally value-events across the run's cycles:

| axis         | productive event                               | never flagged? |
|--------------|------------------------------------------------|----------------|
| implementer  | always (the point)                             | yes — core     |
| verifier     | always (the gate)                              | yes — core     |
| logic        | `logic_ok is False` ≥1 (caught what verify missed) | no          |
| advisor      | `advised is True` (rescued a FAIL)             | no             |
| e2e          | `e2e_ok is False` (caught a live behavioral FAIL)  | no          |
| simplifier   | `simplified is True` (cleanup stuck past re-verify) | no        |
| test-writer  | `test_written is True`                         | no             |

`ROI = role_tokens / max(value_events, 1)`. Ranking: idle axes with high token spend
rank worst → surfaced as prune candidates **for this domain/run**.

**Honesty rules** (mirror `trajectory.py` / prune law):
- A role with **no measured tokens** (telemetry off, or a codex-backed axis whose
  runner has no telemetry) → shown "unmeasured", excluded from token-ROI ranking,
  **never estimated** (a guess must not wear a measured metric's clothes — that lives
  in `sigma cost`).
- Zero value-events **and** zero tokens → not flagged (no evidence either way — prune
  law: never act on absent evidence).
- Wording is run-scoped: "0 catches in this run", never "useless" — a logic axis that
  caught nothing across 5 easy cycles isn't proven worthless.

## Architecture & data flow

Single source of truth = `trajectory.jsonl` (already written per run). Two projections
over it:

```
trajectory.jsonl
  ├─ non-cycle steps (role=implementer/verifier/logic/…) → tokens + count per role
  └─ role="cycle" steps  → per-axis value tallies (NEW effect fields, see below)
                                    │
                                    ▼
                          build_economy(steps) → AxisEconomy (pure, deterministic)
                                    │
                                    ▼
                          render() → markdown report (ranked, flagged)
```

**Plumbing (chosen: option A — extend the existing cycle step, no new file).**
`record_cycle_steps` (`cli/loop.py`) already emits one `role="cycle"` step per
`CycleOutcome` carrying `ok`/`domain`/`lessons`. Extend it to also carry the per-axis
effect flags it already has in scope: `logic_ok`, `advised`, `e2e_ok`, `simplified`,
`test_written`. Then `axis_economy` reads **only** `trajectory.jsonl` — one source,
works after the fact, works for `--team` (thread interleave is irrelevant to a
role-level aggregate). Rejected option B (separate `outcomes.jsonl`) = two sources to
keep in sync.

`TrajectoryStep` gains these optional fields (same additive pattern it already used for
`domain`/`lessons`); `build_step` parses them lenient (absent → None, so trajectories
written before this change still read — back-compat). Pure projection stays pure.

### New module: `cli/axis_economy.py`

- `@dataclass AxisRow`: `role`, `token_total: Optional[int]`, `runs: int`,
  `value_events: int`, `is_core: bool`, `measured: bool`, `roi: Optional[float]`,
  `flag: Optional[str]` (e.g. "prune candidate: idle this run").
- `@dataclass AxisEconomy`: `rows: List[AxisRow]`, `total_measured_tokens: int`,
  `cycles: int`; `.render() -> str`; ranks worst-ROI idle axes first in a "review"
  section, cores + productive axes in an "earning" section.
- `build_economy(steps: List[TrajectoryStep]) -> AxisEconomy`: pure. Folds non-cycle
  steps into per-role token/count; folds `role="cycle"` steps into per-axis value
  tallies via the value model above. Division-guarded (`max(events, 1)`).

### CLI surface

`sigma trajectory --economy` (a flag on the existing `trajectory` command, mirroring
`--efficiency` — same topic resolution, same `read_steps(ws)` input, same
print-to-stdout shape). `--json` composes with it. **Deviation from the brainstorm's
"new command"**: strictly less surface, identical inputs, consistent with the sibling
report — adopted for minimalism. No plugin slash command in Stage 2 (CLI-only, like
`trajectory`/`cost`).

## Error handling / edge cases (all fail-safe)

- Missing/empty `trajectory.jsonl` → "No trajectory data yet. Run `sigma loop --execute` first."
- Corrupt lines → skipped by the existing lenient `read_steps`.
- Role has cycle steps but zero measured tokens → "unmeasured", excluded from ranking, not estimated.
- Zero value-events + zero tokens for a role → not listed as a candidate (no evidence).
- Division guarded everywhere (`max(events, 1)`).
- Never raises; `cmd_trajectory` already returns 1 only on missing workspace, else 0 — a report tool must not break a session.

## Testing (pure, no agents)

`build_economy` + `render` with hand-built `TrajectoryStep` lists:
- productive axis (logic caught a fail) ranks as earning;
- idle axis (logic ran N cycles, 0 catches, real tokens) flagged prune candidate;
- unmeasured axis (cycle steps present, no token telemetry) shown unmeasured, unranked;
- empty input → "no data" line;
- division-by-zero guard (axis with tokens, 0 cycles);
- **back-compat**: a `role="cycle"` step written WITHOUT the new effect fields → all
  value tallies degrade to "unmeasured"/None, never a KeyError.

`record_cycle_steps` test: asserts the new effect fields are populated from `CycleOutcome`.
Whole suite (924) stays green + new cases.

## Out of scope (YAGNI — deferred to later stages)

- Per-cycle attribution (needs a cycle id on every trajectory step — Stage 3 if the role-level report proves too coarse).
- LM-judged value (self-defeating for a token-saving tool; rejected in brainstorm).
- Auto-disable of idle axes (violates prune's surface-never-act law).
- Cross-run trend / historical ROI.
- The Stage-3 optimizations themselves (simplifier skip-reverify on NO-CHANGES, cross-axis prompt-cache prefix, routing idle axes cheaper) — this spec only builds the evidence for them.
