---
command: /propose
description: Synthesize research into 2-3 candidate approaches with trade-offs and a recommendation
stage: 2
inputs: ["sigma/specs/{date}-{slug}/research.md"]
outputs: ["sigma/specs/{date}-{slug}/proposals.md"]
---

# /propose

Turn research into **decision-ready options**.

## Optional front-end: brainstorm first

`/propose` defaults to synthesizing the existing `research.md` one-shot. When the
requirements themselves are still fuzzy (not just the approach), run the
`superpowers:brainstorming` skill FIRST — an interactive, one-question-at-a-time
dialogue that pins purpose, constraints, and success criteria before options are
drawn. Use brainstorm when there is no clear spec yet; skip it (go straight to the
behavior below) when `research.md` already frames the problem well. Brainstorming
is a front-end to this stage, not a replacement — its output feeds the synthesis.

## Behavior

1. Read `research.md`.
2. Produce **2-3 distinct approaches**. For each:
   - One-line summary
   - How it works
   - Trade-offs (pros / cons)
   - Cost, risk, and effort estimate
   - Which `sigma` domains it touches
3. Lead with a **recommendation** and the reasoning.
4. Write `proposals.md`.

## Rules

- Approaches must be genuinely distinct, not variations of one idea.
- YAGNI: strip speculative features.
- Be explicit about what each option does NOT do.

## Next

→ `/blueprint` (after the human picks an approach)
