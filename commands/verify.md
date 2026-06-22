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

## Eval axis — for generative / ML outputs (not just binary)

Some outputs are **generated, not computed**: an LLM/agent/classifier/summariser
can pass 100 unit tests on its tools and still choose the wrong tool, paraphrase a
critical answer, or hallucinate. Binary assertions miss this. For tasks whose
output is model-generated, ADD a scored eval alongside the PASS/FAIL checks:

- **Scored judgment** — LLM-as-judge gives a **0–5** score vs a baseline/rubric
  ("is behaviour at least as good as baseline?"), not just true/false.
- **Tolerance band** — the gate fires when quality drops **below a configured
  margin**, not when an exact assertion flips (accommodates inherent model variance).
- **Trajectory check** — for agents, verify the tool-call path, tolerating
  ordering variance where it doesn't change the outcome.

Tests catch deterministic regressions; eval catches **behavioural drift**. Report
the eval score + threshold in `verify/{task_id}.md`; a below-margin score is a FAIL.

## Rules

- Verifier is a **separate agent** from the implementer (no self-grading).
- Default to skeptical; demand evidence.
- Quote exact errors.
- Eval scores are evidence too — record the score, the threshold, and the judge.

## Next

→ pass: next task · fail: fix loop
