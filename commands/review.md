---
command: /review
description: Three-axis review of a team change set (local diff or PR) — code, ML-logic, system-logic — grounded in the logic profile + past lessons
stage: aux
inputs: ["PR number/URL or git range (optional; default = local diff vs HEAD)", "sigma/profile/logic-profile.md", "skills/"]
outputs: ["sigma/reviews/{slug}/review.md", "PR summary comment (PR mode)"]
---

# /review

Review a **team-authored change** through three **distinct** agents. Maker ≠
checker applies across axes: each axis is its own reviewer, none self-grades.

## Resolve the change set
- No argument → local diff: `git diff HEAD` (working tree + staged).
- A git range `a..b` → `git diff a..b`.
- A PR number/URL → `gh pr diff <ref>`.
If the diff is empty: stop, "nothing to review" (not a failure).

## Ground it (read, do not regenerate)
1. Read `sigma/profile/logic-profile.md` if present. If absent → proceed on diff +
   lessons only, and say so. If it is OLDER than the changed files → warn it may be
   stale (proceed anyway).
2. Infer the touched domain(s) from the file paths; recall past lessons for those
   domains (the `sigma-lessons` skill) and the domains' `logic-evaluator.md`.

## Run three axes (distinct agents, same context bundle)
1. **code** — bugs, security, error handling, conventions.
2. **ml-logic** — apply the domain `logic-evaluator.md` to the change against the
   profile's ML-logic invariants: broken splits/leakage guards, silent metric/loss
   changes, reward errors, eval non-determinism, train/serve skew.
3. **system-logic** — control-flow soundness, data-contract/schema breaks,
   concurrency & state coherence, API-boundary compatibility, failure handling.

Each axis reports findings, one per line, EXACTLY:
```
FINDING | <CRITICAL|HIGH|MEDIUM|LOW> | <file>:<line> | <one-line message>
```
and ends with `VERDICT: PASS` or `VERDICT: FAIL`.

## Verdict & outputs
- Aggregate + dedup findings by `file:line`.
- **Gate FAILs on any CRITICAL/HIGH finding, or any inconclusive axis** (a silent
  axis is never a pass).
- Always write `sigma/reviews/{slug}/review.md`. In PR mode, also post a short
  summary comment via `gh pr comment`.
- Ratchet every CRITICAL/HIGH finding into `skills/` (recalled on the next review).

## Cost
Heavy op (three axes). Before running, note the `sigma-cost` advisory: route the
`code` axis to a cheap model, reserve a strong model for `ml-logic`.

## Next
→ pass: ship · fail: fix CRITICAL/HIGH (now ratcheted), re-run `/review`
