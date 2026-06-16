---
command: /propose
description: Synthesize research into 2-3 candidate approaches with trade-offs and a recommendation
stage: 2
inputs: ["sigma/specs/{date}-{slug}/research.md"]
outputs: ["sigma/specs/{date}-{slug}/proposals.md"]
---

# /propose

Turn research into **decision-ready options**.

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
