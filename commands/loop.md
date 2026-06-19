---
command: /loop
description: Autonomous loop — discover, implement, verify, ratchet failures into skills; supports test-first (TDD), parallel tasks (team), and a logic-evaluator axis
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

## Modes

These work BOTH in-session (here, via subagents) and from the CLI
(`sigma loop --execute --tdd --team --logic`). When the user asks for a mode in
Claude Code, apply it by dispatching the right subagents — no flags needed.

### TDD (test-first) — when asked to "do it test-first" / "TDD"

Per task, run a strict RED→GREEN with **distinct subagents**:

1. **Test-writer subagent** — writes a FAILING test that pins the task's
   acceptance criteria. It must NOT implement the feature; the test fails because
   the feature is absent (not a syntax error). Save it under `tests/`.
2. **Implementer subagent** (distinct) — receives that failing test and makes it
   pass WITHOUT weakening what it checks (do not edit the test to fit the code).
3. **Checker subagent** (distinct) — verifies, separate from both above.

One agent tests, another codes, a third checks — never the same agent twice.

### Team (parallel tasks) — when asked to "do these in parallel" / "as a team"

For INDEPENDENT tasks (no shared files / ordering), dispatch their cycles
concurrently — send the implementer subagents in a SINGLE message (multiple Task
calls in one turn). Recall the domain's past lessons ONCE up front and pass the
same block to each (so parallel work is consistent). Serialize any tasks that
touch the same files.

### Logic axis — when correctness of *reasoning* matters

Add a third distinct **logic-evaluator subagent** (per the domain
`logic-evaluator.md`): it grades plan↔implementation coherence, not style. The
cycle passes only when BOTH the code checker AND the logic evaluator pass.

Combine freely: parallel tasks, each test-first, each triple-checked.

## Guardrails (non-negotiable)

- **Maker/checker separation** — never let the implementer grade itself.
- **Budget cap** — hard ceiling on cycles / spend; stop when reached.
- **Persistent external state** — markdown is the memory across cycles.
- **Human stays the engineer** — verification burden and comprehension are yours;
  the loop amplifies intent, it does not replace understanding.

## Next

→ review queue · `/create-pr`-style handoff
