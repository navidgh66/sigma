---
command: /implement-task
description: Implement one task with its domain context-engine loaded; supports test-first (TDD, distinct test-writer) and parallel multi-task work
stage: 6
inputs: ["sigma/specs/{date}-{slug}/tasks.md", "task_id"]
outputs: ["implementation", "sigma/specs/{date}-{slug}/impl/{task_id}.md"]
---

# /implement-task

Implement a single task with **only the relevant domain context** loaded.

## Behavior

1. Read `tasks.md`, select `task_id`.
2. Load that task's domain context-engine (`implementers/` for the domain).
3. Read the task's **BDD scenarios** from the spec (Scenario / Given / When /
   Then). These are the behavioral contract — implement to satisfy each
   State → Action → Outcome, not just the acceptance criteria title.
4. Implement to deliver every scenario. Search the codebase before assuming
   anything is missing (ripgrep-first).
5. Write a short `impl/{task_id}.md` note: what changed, why, which scenarios
   it satisfies, how to verify.

## TDD mode — when asked to "do it test-first" / "TDD"

Mirror `sigma loop --tdd`: write the test FIRST with a **distinct agent** from the
implementer (one tests, another codes).

1. **Test-writer subagent** — writes a FAILING test derived directly from the
   task's **BDD scenario** (Given → setup, When → action, Then → assertion).
   It must NOT implement the feature; the test fails because the feature is
   absent (not a syntax error). Save under `tests/`.
2. **Implementer** (distinct, step 3 above) — receives that failing test and makes
   it pass WITHOUT weakening it (do not edit the test to fit the code).
3. Note the test-first artifact in `impl/{task_id}.md`.

Then hand to `/verify` (still a separate checker — maker ≠ checker).

## Forensic mode — when the task is a BUG FIX

When things break, switch from building to forensics. Goal: root-cause analysis
and a **surgical** repair, nothing more.

1. **Evidence, not symptoms** — work from evidence, not a vibe. Not "the button
   doesn't work" but "logs (`<exact command>`) show a 403 at the auth step." Trace
   the flow explicitly: "request → load balancer → auth strips header → pod fails."
2. **Failing repro FIRST** — write a failing unit test or a `curl`/CLI repro that
   reproduces the bug BEFORE any fix (a distinct step, like `--tdd`). Keep it in
   the codebase so the bug can't silently return.
3. **Root cause only** — fix the root cause and nothing else. Do NOT "clean up"
   unrelated code or rename variables in the same change (that complicates review;
   renames are a separate task).
4. Note the repro + root cause in `impl/{task_id}.md`.

Then hand to `/verify` (separate checker — maker ≠ checker).

## Multiple tasks in parallel ("team")

`/implement-task` is single-task. To work several INDEPENDENT tasks at once
(non-overlapping files), dispatch one implementer subagent per task in a SINGLE
message (parallel Task calls) — the in-session equivalent of `sigma loop --team`.
Serialize any tasks that share files. Each still gets its own `/verify`.

## Rules

- Load only the domain that owns the task — keep context lean.
- Follow existing codebase patterns.
- Match surrounding code style.
- Make the smallest change that satisfies the criteria.
- TDD: the test-writer and implementer must be DISTINCT agents.

## Next

→ `/verify`
