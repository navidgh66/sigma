---
command: /grill
description: Adversarially grill a design (blueprint) or spec before the pipeline advances — a skeptical reviewer distinct from the author, blocking on logic flaws
stage: gate
inputs: ["sigma/specs/{date}-{slug}/architecture.md OR spec.md", "--target blueprint|spec (optional; inferred)"]
outputs: ["sigma/specs/{date}-{slug}/grill/{target}.md", "verdict: READY | BLOCK"]
---

# /grill

**Grill the design before code exists.** A logic flaw caught in the spec costs a
sentence to fix; the same flaw caught after the agent has generated a thousand
lines costs a rewrite. `/grill` is the adversarial gate that interrogates an
artifact — and, like `/verify`, it **defaults to BLOCK on doubt**.

> "You'd much rather have a human catch a logic flaw in your design than wait
> until the AI has already generated thousands of lines of broken code."
> — *Spec-Driven Production-Grade Development in the Age of Vibe Coding* (Boonstra, 2026)

Maker ≠ griller: the griller is a **separate agent** from whoever authored the
artifact. Never let the author grill its own work (same law as `execute_cycle`).

## Pick the target

Two gates, one mechanism. Infer from `--target`, else from what exists:

- **blueprint** → grills `architecture.md` (design-level: boundaries, coupling,
  risks, missing components). Runs after `/blueprint`, before `/spec`.
- **spec** → grills `spec.md` (implementation-ready: ambiguity, untestable
  criteria, missing edge/error paths, ML risks). Runs after `/spec`, before `/tasks`.

If the target artifact is absent → **BLOCK** (can't grill nothing); surface to
human. Fail-safe, not silent.

## Behavior

1. Load the target artifact and its prior-stage context (chain back one stage).
2. Load the `sigma-grilling` skill (the rubric) and, for ML-bearing work, the
   touched domains' `logic-evaluator.md` (via `sigma-domains`) + past lessons
   (via `sigma-lessons`).
3. Interrogate the artifact against the rubric's axes (see `sigma-grilling`):
   ambiguity, hidden assumptions (pre-mortem), testability, edge/error paths,
   scope, ML/data risk, plus the spec-quality checks (BDD scenarios present,
   "why behind the what", pinned versions, format/token discipline).
4. Write `grill/{target}.md`: findings + verdict.

## Findings & verdict (skeptical, sigma-idiomatic)

Each finding, one per line, EXACTLY (same shape as `/review`):
```
FINDING | <CRITICAL|HIGH|MEDIUM|LOW> | <artifact section/anchor> | <one-line issue + what to add/decide>
```
End with `VERDICT: READY` or `VERDICT: BLOCK`.

- **BLOCK** on any CRITICAL/HIGH finding, OR if the grill is inconclusive (a
  dead/silent pass is never READY — skeptical, like `_verdict_pass`).
- **READY** only when clean of CRITICAL/HIGH.

## Gate (blocking, human override)

- On **BLOCK** → do NOT advance. Feed findings back to `/blueprint` or `/spec` to
  revise, then re-grill (the grill↔author loop, mirroring verify→implement).
- A human MAY override a BLOCK to proceed — but the override is explicit and
  recorded in `grill/{target}.md`. The gate never silently passes itself.

## Rules

- Griller is a **separate agent** from the author — no self-grading.
- Demand evidence; quote the exact ambiguous/untestable line.
- Don't rewrite the artifact — name the flaw and what must be decided/added.
- YAGNI: no auto-fix, no new CLI subcommand (stages are plugin-only).

## Next

→ READY: `/spec` (after blueprint-grill) · `/tasks` (after spec-grill)
→ BLOCK: revise the artifact, re-run `/grill` — or `/grill-loop` to auto-drive
  grill→edit→re-grill (mechanical fixes auto-applied, CRITICAL/intent surfaced).
