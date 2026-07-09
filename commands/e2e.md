---
command: /e2e
description: Run spec.md's BDD scenarios end-to-end against a live instance of the target app
stage: aux
inputs: ["sigma/specs/{date}-{slug}/spec.md"]
outputs: ["sigma/specs/{date}-{slug}/e2e-report.md"]
---

# /e2e

Run every **Scenario / Given / When / Then** block in `spec.md` **live**
against a running instance of the target app — not just reasoning about the
code, actually driving it.

## Behavior

1. Resolve the workspace: no argument → the most recently modified
   `sigma/specs/{date}-{slug}/` directory containing a `spec.md`.
2. Extract every `Scenario:/Given/When/Then` block from `spec.md`.
3. **Launch the app** — invoke the `run` skill (it detects whether the app is
   already live and starts it if not).
4. For each scenario, perform **Given** (starting state) and **When** (the
   action) using whatever tool fits: browser automation for a web UI, HTTP
   calls for an API, subprocess invocation for a CLI. Then check **Then** and
   assign a verdict:
   - `PASS` — ran to completion, Then held.
   - `FAIL` — ran to completion, Then's assertion was false. A real behavior
     bug.
   - `ERROR` — could not complete Given/When (app unreachable, tool crash,
     timeout). Inconclusive — NOT a behavior verdict.
5. Write `sigma/specs/{date}-{slug}/e2e-report.md`: one row per scenario —
   name | verdict | evidence (screenshot ref / response body / stdout
   excerpt) — plus an overall summary.
6. **Ratchet**: every `FAIL` (never `ERROR` — no lesson from absent evidence)
   writes a lesson via the exact `/sigma-learn-lesson` format (domain-tagged),
   so `sigma loop --e2e` and `/implement-task` recall it next time.

## Report format

```markdown
# E2E Report — {workspace slug}

| Scenario | Verdict | Evidence |
|---|---|---|
| user signs up | PASS | screenshot: signup-success.png |
| null input rejected | FAIL | expected 400, got 500 — see response.json |
| dependency unavailable | ERROR | app unreachable on :3000 after 30s |

**Summary:** 1 PASS / 1 FAIL / 1 ERROR — not clean.
```

## Rules

- One agent per scenario drives Given/When AND checks Then — no actor/judge
  split (mirrors how a human tester works a scenario end to end).
- Never fabricate a PASS. An incomplete Given/When is ERROR, not a guess.
- Ratchet FAIL only — an ERROR is absent evidence, not a lesson.

## Next

→ all PASS: ship · any FAIL: fix impl (lesson ratcheted), re-run `/e2e` · any
ERROR: fix the environment, re-run.
