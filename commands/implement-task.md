---
command: /implement-task
description: Implement one task with its domain context-engine loaded (human in the loop); supports test-first (distinct test-writer agent), a test tamper guard, and parallel multi-task work
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
4. Snapshot the existing tests:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_guard.py" snapshot <workspace>/.test-snapshot-<task_id>.json`
5. Implement to deliver every scenario (directly, or by dispatching the
   `sigma-implementer` agent). Search the codebase before assuming anything is
   missing (ripgrep-first).
6. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_guard.py" check <snapshot>`.
   Any path it prints is a pre-existing test that was edited or deleted: restore it
   and fix the code instead. If you believe the test itself is wrong, say which one
   and why, and let the user decide.
7. Write a short `impl/{task_id}.md` note: what changed, why, which scenarios
   it satisfies, how to verify.

## E2E scenario check — if this task has a mapped Scenario

If `tasks.md` tags this task with `[scenario: <name>]` (or `scenarios:`),
dispatch the `sigma-e2e` agent with that scenario (the same check `/e2e` runs):
it launches the app via the `run` skill if needed, drives Given/When for real,
checks Then, and returns PASS/FAIL/ERROR. Record the verdict in
`impl/{task_id}.md`.

- `PASS` — proceed to `/verify`.
- `FAIL` — the task is not actually done. Do not consider it complete
  until the scenario passes. Fix the implementation and re-run this check.
- `ERROR` — an environment issue (app unreachable, tool crash), not a
  behavior bug. Note it and retry before moving to `/verify`; do not block
  completion on an ERROR the way a FAIL blocks it.

This runs the mapped scenario once for this task, not the full spec suite
(that's what `/e2e` is for).

## TDD mode — when asked to "do it test-first" / "TDD"

Same as `/loop`'s test-first step: the test comes first, from a distinct agent
(one tests, another codes).

1. Dispatch `sigma-test-writer`: it writes a failing test derived from the task's
   BDD scenario (Given → setup, When → action, Then → assertion) and confirms it
   fails because the feature is absent, not because of a syntax error.
2. Take the test snapshot (Behavior step 4) after the test exists, so it is
   protected too.
3. Implement (Behavior step 5): make that test pass without weakening it.
4. Note the test-first artifact in `impl/{task_id}.md`.

Then hand to `/verify` (still a separate checker — maker ≠ checker).

## Forensic mode — when the task is a BUG FIX

When things break, switch from building to forensics. Goal: root-cause analysis
and a **surgical** repair, nothing more.

1. **Evidence, not symptoms** — work from evidence, not a vibe. Not "the button
   doesn't work" but "logs (`<exact command>`) show a 403 at the auth step." Trace
   the flow explicitly: "request → load balancer → auth strips header → pod fails."
2. **Failing repro first** — write a failing unit test or a `curl`/CLI repro that
   reproduces the bug before any fix (a distinct step, like test-first mode). Keep it in
   the codebase so the bug can't silently return.
3. **Root cause only** — fix the root cause and nothing else. Don't "clean up"
   unrelated code or rename variables in the same change (that complicates review;
   renames are a separate task).
4. Note the repro + root cause in `impl/{task_id}.md`.

Then hand to `/verify` (separate checker — maker ≠ checker).

## Build discipline (every task)

**Reuse-first laziness ladder** — before writing any new code, walk this ladder
in order and stop at the first hit (be lazy about the *solution*, never about
understanding the problem — still read and trace the real flow first):

1. Does it need to exist at all? (YAGNI — if not, skip it)
2. Already in this codebase? → reuse it, don't re-implement
3. In the standard library? → use it
4. A native platform / framework feature? → use it
5. An already-installed dependency? → use it
6. A one-liner? → write the one-liner
7. Only then → the smallest working implementation

Record any shortcut you defer (a "do it later") in `impl/{task_id}.md` so "later"
doesn't become "never".

**No-YOLO on from-scratch scaffolds** — if the task creates a new project/module
skeleton, don't generate code immediately. Propose the folder structure + stack
(with **pinned versions**) and confirm first. Include tests, docs, and logging in
what you scaffold — not just the happy-path code.

**Docs-as-truth** — if the change touches a documented module, update its
`README` / docstrings / `CHANGELOG` in the same task. Out-of-sync docs make the
agent hallucinate on the next run; the docs are part of the deliverable.

## Multiple tasks in parallel ("team")

`/implement-task` is single-task. To work several independent tasks at once
(non-overlapping files), dispatch one `sigma-implementer` per task in a single
message with `isolation: worktree` (same as `/loop`'s parallel mode).
Serialize any tasks that share files. Each still gets its own `/verify`.

## Rules

- Load only the domain that owns the task — keep context lean.
- Follow existing codebase patterns.
- Match surrounding code style.
- Make the smallest change that satisfies the criteria.
- Test-first: the test-writer and implementer are different agents.
- Existing tests are the contract; the tamper guard checks them.

## Next

→ `/verify` (the `sigma-verifier` agent: separate checker, no edit tools), or `/loop` to run every open task
