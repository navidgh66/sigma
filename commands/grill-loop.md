---
command: /grill-loop
description: Auto-grill loop — grill a spec/blueprint, auto-apply mechanical fixes, gate CRITICAL/judgment findings to a human, re-grill, until READY or a round cap
stage: gate
inputs: ["sigma/specs/{date}-{slug}/architecture.md OR spec.md OR an explicit path", "--target blueprint|spec (optional)", "--rounds N (default 3)"]
outputs: ["grill/{target}-r{k}.md per round", "revised artifact", "verdict: READY | SURFACED"]
---

# /grill-loop

Bounded **grill → triage → edit → re-grill** loop. Drives an artifact toward
READY without a human babysitting every round — while keeping the spec's INTENT
safe (only mechanical fixes auto-apply; anything that could change meaning is
surfaced, not silently rewritten).

This is `/loop`'s maker→checker discipline applied to a **spec instead of code**:

> design the loop, stay the engineer. The loop amplifies intent; it never
> replaces your judgment about what the spec should *mean*.

## The two-agent law (non-negotiable)

**Editor ≠ griller.** Two distinct agents, never the same one twice in a round:
- **Editor subagent** (the maker) — revises the artifact against findings.
- **Griller subagent** (the checker) — re-grills, per `sigma-grilling`.

A single agent that both edits and grades games its own test (same separation
`execute_cycle` enforces via `ValueError`).

## Autonomy — mechanical-only auto, gate the rest

Each round, classify every finding before touching the artifact:

- **AUTO (apply)** — mechanical, meaning-preserving fixes:
  - add a missing BDD Scenario/Given/When/Then for a described behavior
  - pin a library/model version
  - define an undefined term already used unambiguously
  - add an explicit edge/error case the spec clearly implies
  - add an explicit out-of-scope line for something already excluded in prose
  - format/token discipline (nested config → flat YAML)
- **SURFACE (do NOT auto-edit)** — anything that could change intent:
  - every **CRITICAL** finding
  - contradictory requirements (which reading is right is a human call)
  - missing acceptance criteria where the *target value* is a judgment (thresholds)
  - scope decisions (is this in or out?)
  - anything the editor is <90% sure preserves meaning

The editor applies only AUTO fixes. SURFACE findings go to a human queue with the
exact question to answer — the loop never guesses intent.

## The loop

```
round k (1..N):
  1. griller subagent grills the artifact  → grill/{target}-r{k}.md
  2. if VERDICT READY → stop (READY)
  3. triage findings → AUTO vs SURFACE
  4. editor subagent (distinct) applies AUTO fixes to the artifact
  5. record applied edits + the SURFACE queue in the round report
  6. convergence check (below) → maybe stop early
stop → emit final verdict + the human queue
```

## Convergence (so it never thrashes)

- **Round cap** — default 3 (`--rounds N`). Hard ceiling.
- **No-progress stop** — if `CRIT+HIGH` count does NOT drop vs the previous round,
  stop immediately. A finding that survives an honest edit is a judgment call or a
  griller false-positive — surface it, don't loop on it.
- **All-SURFACE stop** — if a round has zero AUTO fixes (everything left needs a
  human), stop and surface. Nothing mechanical remains to do.

## Final verdict

- **READY** — griller passed within the cap. Artifact revised in place; the trail
  is `grill/{target}-r1..rk.md`.
- **SURFACED** — hit a stop condition with findings remaining. Emit:
  - the human queue: each SURFACE finding + the exact decision needed
  - the per-round CRIT+HIGH trend (did it converge or stall?)
  Never reported as READY — a surfaced loop is honest about what's unresolved
  (skeptical, like `_verdict_pass`).

## Rules

- Editor and griller are **distinct agents** every round (no self-grading).
- Auto-edits are **mechanical only** — meaning-changing edits are surfaced.
- Every round writes a report; every applied edit is logged (auditable trail).
- A human may accept a SURFACED artifact as-is (override recorded in the report).
- Don't delete or rewrite prose wholesale — minimal, additive fixes.

## Next

→ READY: `/tasks` (spec) or `/spec` (blueprint)
→ SURFACED: answer the human queue, re-run `/grill-loop` (or fix + single `/grill`)
