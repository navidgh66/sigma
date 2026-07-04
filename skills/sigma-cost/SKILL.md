---
name: sigma-cost
description: >
  Estimate, measure, and optimize token cost for sigma's heavy operations (review's
  three axes, the profile walk, loop cycles, multi-model research). Use before
  running a heavy op to size it and pick model tiers, and after to record actual
  spend and report trends. Triggers: "how expensive", "estimate cost", "which model
  should this axis use", "what's burning tokens", "sigma cost", or before any
  multi-axis review / loop / deep research run.
origin: sigma
---

# sigma-cost

A closed cost loop for sigma's heavy ops: **estimate before → measure after →
sharpen next**. The pure logic lives in `cli/cost.py`; this skill is the in-session
side that reads the same ledger (`sigma/costs.jsonl`) and advises.

## Boundaries (compose, don't duplicate)
- **RTK** cuts token *overhead* at the proxy layer (transparent command rewriting).
- **caveman** trims *output* verbosity.
- **sigma-cost** estimates/measures/routes sigma's own *operations*. It may
  *recommend* enabling RTK or caveman when it detects waste — it does not replace
  them.

## Before a heavy op (estimate + route)
1. Size the work in **units**: review = axes × changed files; profile = files
   walked; loop = cycles; research = models.
2. Estimate tokens: `units × tokens-per-unit`. Use the calibrated factor from
   `sigma/costs.jsonl` when present; otherwise the static fallback.
3. **Route by reasoning load** (performance.md strategy):
   - `code` axis, mechanical edits → **haiku** (cheap).
   - `system-logic`, orchestration → **sonnet**.
   - `ml-logic`, hardest reasoning → **opus**.
4. Skip work that adds no value: a stale-but-cheap profile refresh, an axis with no
   relevant files.

## After a heavy op (measure)
Append one row to `sigma/costs.jsonl` (append-only, like `events.jsonl`):
`{"ts", "op", "units", "tokens", "estimated", "models"}`. The caller supplies the
timestamp (deterministic projection — never generated in pure code).

## Report
`sigma cost` renders per-op totals, biggest token sinks, and est-vs-actual drift
(which shrinks as calibration kicks in). Use it to decide where routing or RTK pays
off most.

## Efficiency (in-session, no CLI needed)
`sigma trajectory --efficiency` (or read `trajectory.jsonl` directly in-session,
the same way this skill already reads `sigma/costs.jsonl` without shelling out)
answers a DIFFERENT question than the cost ledger: not "how many tokens did this
burn" but "is the loop actually working, and is escalation earning its keep."

Read the current spec workspace's `trajectory.jsonl` and report:
- **Cycle pass rate** — the fraction of `role: "cycle"` steps with `ok: true` (one
  such step is appended per completed `execute_cycle`, real verified/not-verified
  data, not a token guess).
- **Escalation rate** — `(logic + advisor + test-writer + simplifier steps) /
  implementer steps`. High and climbing → the expensive axes are firing often;
  worth checking whether `--advisor-rounds` or `--logic` are pulling their weight.
- **Crash rate** — subprocess exit failures across all roles. **Not the same as a
  verify-fail**: a verifier returning `VERDICT: FAIL` still exits 0, so this
  measures agent-CLI crashes, not verification quality.

**Do NOT report a token-per-cycle number here.** `claude -p` never surfaces real
token usage, so any per-cycle token figure would be `units × static_factor`
wearing a measured metric's clothes — it never calibrates (see `calibrate()`
above) and collapses to a restatement of the pass rate. If asked "how many tokens
per successful cycle," say plainly that sigma has no real per-run token signal
today and point to the pass-rate/escalation-rate numbers instead, or to `sigma
cost`'s explicitly-labeled *estimate* if a rough order-of-magnitude is wanted.

## Fail-safe
A missing or corrupt ledger falls back to static estimates and **never blocks** the
op (the inverse of a hard gate). Estimates are advisory — the operator keeps the
wheel (loop-engineering principle). Empty/missing `trajectory.jsonl` → "no data
yet", never a crash — same discipline.
