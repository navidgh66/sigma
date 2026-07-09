---
command: /tasks
description: Break the spec into domain-routed, independently-implementable tasks
stage: 5
inputs: ["sigma/specs/{date}-{slug}/spec.md"]
outputs: ["sigma/specs/{date}-{slug}/tasks.md"]
---

# /tasks

Decompose the spec into a **task breakdown** routed by domain.

## Behavior

1. Read `spec.md`.
2. Produce `tasks.md` — an ordered, checkbox task list. For each task:
   - ID + title
   - **Domain** (which `sigma` context-engine implements it:
     classic-ml / deep-learning / nlp / rl / data-analysis /
     data-engineering / ai-agent-engineering / mlops / llm-engineering)
   - **Scenarios** — the exact `spec.md` `Scenario:` name(s) this task must
     satisfy, as an inline tag on the task line: `[scenario: <name>]` for one,
     `[scenarios: <name1>, <name2>]` for several. Leave the tag off entirely
     for tasks with no user-facing flow (e.g. a pure backend utility) — not
     every task maps to a scenario. Example:
     `- [ ] T3 (nlp) [scenario: null input rejected]: validate input`
   - Pre-discovered context (files, interfaces it touches)
   - Acceptance criteria for that task
   - Dependencies (which tasks must precede it)
3. Mark which tasks can run in **parallel** (no shared state).

## Rules

- Each task is independently implementable and verifiable.
- Right granularity — not too big, not trivial.
- Surface ordering and dependencies explicitly.
- A task whose scenario tag names something not present in `spec.md` is a
  spec/tasks mismatch — fix the tag or the spec before proceeding.

## Next

→ `/implement-task <id>` or `/loop` (pass `--e2e` to gate cycles on each
task's mapped scenario running live)
