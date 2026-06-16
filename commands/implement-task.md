---
command: /implement-task
description: Implement one task with its domain context-engine loaded
stage: 6
inputs: ["sigma/specs/{date}-{slug}/tasks.md", "task_id"]
outputs: ["implementation", "sigma/specs/{date}-{slug}/impl/{task_id}.md"]
---

# /implement-task

Implement a single task with **only the relevant domain context** loaded.

## Behavior

1. Read `tasks.md`, select `task_id`.
2. Load that task's domain context-engine (`implementers/` for the domain).
3. Implement to the task's acceptance criteria.
4. Search the codebase before assuming anything is missing (ripgrep-first).
5. Write a short `impl/{task_id}.md` note: what changed, why, how to verify.

## Rules

- Load only the domain that owns the task — keep context lean.
- Follow existing codebase patterns.
- Match surrounding code style.
- Make the smallest change that satisfies the criteria.

## Next

→ `/verify`
