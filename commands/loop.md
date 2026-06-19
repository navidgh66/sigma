---
command: /loop
description: Autonomous loop — discover, implement, verify, ratchet failures into skills
stage: 8
inputs: ["sigma/specs/{date}-{slug}/tasks.md"]
outputs: ["implementations", "verify reports", "updated skills/", "human review queue"]
---

# /loop

**Loop engineering** — design the loop, stay the engineer.

> "You shouldn't be prompting coding agents anymore. You should be designing
> loops that prompt your agents." — Addy Osmani

## Behavior (per cycle)

1. **Discover** — scan `tasks.md` for the highest-priority incomplete task.
2. **Isolate** — spawn a git worktree for the task (parallel-safe).
3. **Implement** — domain implementer subagent (see `/implement-task`).
4. **Verify** — domain verifier subagent, separate from implementer (`/verify`).
5. **Ratchet** — on failure, encode the lesson into `skills/` so it never recurs
   (the ratchet effect: failures are verbose, success is silent).
6. **Persist** — update task state + a log in `sigma/specs/{slug}/loop-log.md`.
7. **Surface** — unresolved / ambiguous items → human review queue. Stop, don't guess.

Repeat until tasks done, a budget cap is hit, or a task needs human judgment.

## Modes (CLI: `sigma loop --execute [flags]`)

- **default** — sequential cycles, maker→checker.
- **`--tdd`** — a distinct TEST-WRITER agent pens a FAILING test (RED) before the
  implementer, which must make it pass (GREEN) without weakening it. One agent
  codes, another tests, a third checks — all enforced distinct.
- **`--team`** — independent tasks run in PARALLEL (each its own full cycle). The
  recall snapshot is pre-built before fan-out (deterministic, race-free).
- **`--logic`** — add the logic-evaluator axis; a cycle passes only if it passes too.
- Combine freely: `--team --tdd --logic` = parallel tasks, each test-first, triple-checked.

## Guardrails (non-negotiable)

- **Maker/checker separation** — never let the implementer grade itself.
- **Budget cap** — hard ceiling on cycles / spend; stop when reached.
- **Persistent external state** — markdown is the memory across cycles.
- **Human stays the engineer** — verification burden and comprehension are yours;
  the loop amplifies intent, it does not replace understanding.

## Next

→ review queue · `/create-pr`-style handoff
