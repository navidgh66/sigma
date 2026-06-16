---
command: /verify
description: Run domain-specific verification against the spec (separate checker agent)
stage: 7
inputs: ["sigma/specs/{date}-{slug}/spec.md", "task_id"]
outputs: ["sigma/specs/{date}-{slug}/verify/{task_id}.md"]
---

# /verify

**Independently** verify an implementation against the spec. Maker ≠ checker.

## Behavior

1. Load the task's domain `verifiers/`.
2. Run the relevant checks for that domain, e.g.:
   - classic-ml / dl: data leakage, seed determinism, metric correctness
   - nlp: label-scheme + tokenizer/model alignment, eval determinism
   - rl: multi-seed reporting, reward correctness, reward-hacking
   - data-eng: idempotency, schema contracts, freshness
   - mlops: train/serve skew, drift wiring, rollback thresholds
   - ai-agent / llm: eval coverage, tool-schema validity, injection defense
   - tests, types, linters as applicable
3. Write `verify/{task_id}.md`: PASS / FAIL per criterion + evidence.
4. On FAIL → feed back to `/implement-task` (or `/loop` ratchets it).

## Rules

- Verifier is a **separate agent** from the implementer (no self-grading).
- Default to skeptical; demand evidence.
- Quote exact errors.

## Next

→ pass: next task · fail: fix loop
