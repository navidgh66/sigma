---
command: /learn
description: Learn the codebase and persist understanding as ARCHITECTURE.md + a CodeTour walkthrough
stage: aux
inputs: ["persona?", "topic?"]
outputs: ["ARCHITECTURE.md", ".tours/{slug}.tour"]
---

# /learn

Learn this codebase deeply, then persist what you learned as two durable
artifacts a newcomer (or a future agent) can reuse.

Read the project from its root. Then produce, in ONE reply, EXACTLY this structure
— nothing before or after:

```
=== ARCHITECTURE.md ===
<Markdown architecture map: purpose, entry points, module layout, data flow, key
conventions, and where a newcomer should start. Concrete and specific to THIS
repo — name real files and directories.>

=== TOUR.json ===
<a single JSON object in Microsoft CodeTour format: {"title": ..., "steps": [...]}.
Each step has "description" (Markdown) and, when anchoring to code, "file" (path
RELATIVE to the project root) plus EITHER "line" (1-based) OR "pattern" (a
substring that appears on the target line). Anchor every code step to a file that
really exists. Output ONLY the JSON object here — no fence, no commentary.>
```

## Notes
- Prefer `pattern` over `line` when the exact line may drift.
- A step may be description-only (pure narration) with no `file`.
- The CLI validates every anchor (file exists, line in range, pattern present)
  and surfaces any mismatch — keep anchors honest.
- Tailor the walkthrough to the `persona` if one is given (e.g. "new backend dev").
