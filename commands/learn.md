---
command: /learn
description: Learn the codebase and persist understanding as ARCHITECTURE.md + a CodeTour walkthrough
stage: aux
inputs: ["persona?", "topic?"]
outputs: ["ARCHITECTURE.md", ".tours/{slug}.tour"]
---

# /learn

Learn this codebase deeply, then persist what you learned as two durable
artifacts a newcomer (or a future agent) can reuse. **Write both files with the
Write tool** — do not print their contents into the chat and stop. This command
runs in-session; nothing captures your output, so an unwritten artifact is a lost
artifact.

## Behavior

1. Read the project from its root — real files and directories, not a guess.
2. **Write `ARCHITECTURE.md`** at the project root: a Markdown architecture map
   covering purpose, entry points, module layout, data flow, key conventions, and
   where a newcomer should start. Be concrete and specific to THIS repo — name
   real files and directories. Tailor to the `persona` if one is given (e.g.
   "new backend dev").
3. **Write `.tours/{slug}.tour`** — a single JSON object in the Microsoft
   CodeTour format:
   ```json
   {"title": "...", "steps": [ ... ]}
   ```
   `{slug}` is a kebab-case slug of the `topic` (or the tour title, or
   `codebase`). Each step has a `description` (Markdown) and, when it anchors to
   code, a `file` (path RELATIVE to the project root) plus EITHER `line` (1-based)
   OR `pattern` (a substring that appears on the target line).

## Rules

- Anchor every code step to a file that really exists — open it and confirm the
  `line`/`pattern` resolves before writing it. Honest anchors only.
- Prefer `pattern` over `line` when the exact line may drift.
- A step may be description-only (pure narration) with no `file`.
- If a graphify `GRAPH_REPORT.md` is present in the repo, ground the map in it
  (god-nodes, communities, call/import edges).

## Next

→ open the tour with the CodeTour extension, or hand `ARCHITECTURE.md` to a fresh
session. `sigma learn` (CLI) produces the same two artifacts headlessly.
