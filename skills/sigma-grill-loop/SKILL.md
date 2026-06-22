---
name: sigma-grill-loop
description: >
  Run a bounded auto-grill loop over a sigma spec or blueprint — grill, triage
  findings into mechanical-auto-fix vs human-surface, let a DISTINCT editor agent
  apply only the mechanical fixes, re-grill, and repeat until READY or a round
  cap / no-progress stop. Use when running /grill-loop, when a /grill pass came
  back BLOCK with many fixable findings and you want them driven down without
  hand-editing every one, or when the user asks to "auto-fix the spec",
  "iterate the spec to READY", "grill and edit in a loop", or "converge this
  spec". Keeps editor ≠ griller (no self-grading) and never auto-edits intent.
origin: sigma
---

# sigma-grill-loop

The **auto-grill loop** protocol: drive a spec/blueprint toward READY by looping
grill → triage → edit → re-grill, bounded and intent-safe. This is `/loop`'s
maker→checker discipline applied to a spec. It composes with `sigma-grilling`
(the rubric) — this skill is the *control loop* around it.

**Three laws (non-negotiable):**
- **Editor ≠ griller** — two distinct agents per round. The agent that edits the
  spec never grades it (games its own test — same separation `cli/loop.py` enforces).
- **Mechanical-only auto-edit** — only meaning-preserving fixes apply automatically;
  anything that could change intent is SURFACED to a human, never silently rewritten.
- **Bounded + honest** — a hard round cap, a no-progress early stop, and a result
  that is READY only if the griller truly passed (otherwise SURFACED).

## The loop

```
for round k in 1..N (N = round cap, default 3):
  1. GRILL    — griller subagent grills the artifact (sigma-grilling rubric)
                → write grill/{target}-r{k}.md (findings + VERDICT)
  2. READY?   — VERDICT READY → STOP (success)
  3. TRIAGE   — classify each finding: AUTO vs SURFACE (table below)
  4. EDIT     — editor subagent (DISTINCT from griller) applies AUTO fixes only
  5. RECORD   — log applied edits + the SURFACE queue into the round report
  6. CONVERGE — apply the stop checks (below); maybe STOP early
STOP → emit final verdict (READY | SURFACED) + the human queue
```

## Triage rubric — AUTO vs SURFACE

**AUTO** (mechanical, meaning-preserving — editor applies):

| Finding kind | Auto fix |
|---|---|
| Behavior described but no BDD scenario | add Scenario/Given/When/Then for it |
| Library/model unpinned | pin the version |
| Term used unambiguously but undefined | add a definition matching usage |
| Edge/error case the spec clearly implies | add it explicitly |
| Out-of-scope item excluded in prose only | add an explicit out-of-scope line |
| Nested config as prose/JSON | render as flat YAML (format/token discipline) |
| Missing "why" the prose already establishes | add the rationale line |

**SURFACE** (could change intent — human decides, NO auto-edit):

- **Every CRITICAL finding** (correctness/safety — too costly to guess).
- **Contradictory requirements** — which reading wins is a human call.
- **Threshold/target values** — a metric exists but the bar is a judgment (e.g.
  "F1 ≥ ?", "p99 < ?").
- **Scope ambiguity** — genuinely unclear if a thing is in or out.
- **Anything the editor is < 90% sure preserves meaning.**

When unsure → SURFACE. Erring toward surfacing protects intent; erring toward
auto-edit corrupts it.

## Convergence — three ways to stop

1. **READY** — griller passes within the cap. Done.
2. **Round cap** — N rounds elapsed (default 3). Stop, surface remainder.
3. **No-progress** — `CRIT+HIGH` count did not drop vs the prior round. A finding
   that survives an honest edit is a judgment call or a false-positive — surfacing
   beats looping. Stop.
4. **All-SURFACE** — a round produced zero AUTO fixes (only human-decisions left).
   Nothing mechanical remains. Stop.

Track the `CRIT+HIGH` count each round — it is the convergence signal.

## Round report (per round)

Write `grill/{target}-r{k}.md`:
- the griller's findings + VERDICT for this round
- **Applied (AUTO):** each edit made, with the finding it answers
- **Surfaced (human):** each SURFACE finding + the exact decision needed
- the running `CRIT+HIGH` trend

## Final output

- **READY** → artifact revised in place; trail in `grill/{target}-r1..rk.md`.
- **SURFACED** → emit the human queue (decision-needed list) + the per-round trend.
  Never dressed up as READY. A human may accept a SURFACED artifact as-is — that
  override is recorded, never silent.

## Rules

- Distinct editor + griller agents every round.
- Auto-edits are additive and minimal — never wholesale prose rewrites.
- The loop surfaces intent decisions; it does not make them.
- Load only the domain(s) the artifact touches (lean context).
- Pairs with `sigma-grilling` (rubric) and mirrors `/loop` (maker ≠ checker, ratchet).
