---
command: /board
description: Kanban board — project tasks and events into To Do / In Progress / Blocked / Done columns
---

# /board

A **kanban view** of the current feature's work. Pure projection over
`tasks.md` + `events.jsonl` — it never mutates state.

> Full rendering lives in the CLI: `sigma board --topic <t>` (static) or
> `--watch` (live). This command is the in-session equivalent.

## Behavior

1. Read `sigma/specs/{date}-{slug}/tasks.md` (the cards) and `events.jsonl`
   (their latest status).
2. Place each task into a column by its latest event:
   - no event + `- [ ]` → **To Do**
   - `in_progress` → **In Progress**
   - `failed` / `blocked` → **Blocked**
   - `done` or `- [x]` → **Done**
3. Render four columns with each card's id, title, and `(domain)`.

## Card format (from tasks.md)

```markdown
- [ ] T1 (nlp): tokenize corpus
- [x] T2 (mlops): register model
```

## Event format (events.jsonl, one per line)

```json
{"task":"T1","stage":"implement-task","status":"in_progress","ts":"..."}
{"task":"T3","stage":"verify","status":"failed","verdict":"FAIL","ts":"..."}
```

## Next

→ `/loop` advances cards · `/hermes` drives the next stage
