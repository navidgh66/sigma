---
command: /eval
description: Run an eval set — LM-judge each case against its rubric, aggregate a pass rate, gate at a threshold. Set the bar at the eval, not the demo.
stage: aux
inputs: ["sigma/evals/{name}.md (the eval set)", "optional: an artifact to grade instead of running a system-under-test"]
outputs: ["sigma/evals/{name}/report.md", "pass/fail gate decision"]
---

# /eval

Verify the **non-deterministic** half of a system the way tests verify the
deterministic half. A demo proves it can succeed once; a passing eval set proves
it succeeds reliably. The judge is a **distinct** agent from whatever produced the
output (maker ≠ grader — the same law as the loop and review).

## The eval set format

`sigma/evals/<name>.md` — one block per case:

```markdown
# Eval set: <title>

## case: <id>
domain: <domain>          # optional — routes ml grading
input: <the task/prompt to run or the thing to check>
expected: <expected output>   # optional
rubric: <how to judge correctness>   # optional (expected and/or rubric)
```

A case needs an `input` and at least one of `expected` / `rubric`. Inputs and
rubrics may span multiple lines.

## Two modes

1. **Prompt mode** (default): run each case's `input` through a system-under-test
   agent, then grade the output with a distinct judge.
2. **Artifact mode** (`--artifact <file>`): grade an existing file's text against
   every case's rubric — no SUT run. Use this to grade a stage artifact
   (`spec.md`, a report) or any produced file.

## Grade each case (distinct judge)

For each case, the judge sees the input, the criteria (expected + rubric), and the
actual output, then replies EXACTLY:
```
REASON: <one sentence>
VERDICT: PASS  or  VERDICT: FAIL
```
Grading is **skeptical**: a missing `VERDICT: PASS` is a FAIL. A fluent answer that
misses the criteria is a FAIL.

## Verdict & outputs

- Aggregate → pass rate = passed / total.
- **Gate FAILs below the threshold** (default `0.8` — the paper's 80% bar). An
  empty set (no cases ran) is never a silent pass.
- Always write `sigma/evals/{name}/report.md`.
- `--check` exits non-zero below the bar (CI gate, like `review --check`).

## Cost

Heavy op (one SUT run + one grade per case in prompt mode). The `sigma-cost`
advisory routes the judge to a strong tier; the system-under-test can be any tier.

## Next
→ pass: ship / promote the prototype to production · fail: fix the failing cases, re-run `/eval`
