---
command: /claude-md-check
description: Check CLAUDE.md + CLAUDE.local.md against best-practice research (length, pasted code, stale @imports, stale test counts, structure/specificity)
stage: aux
inputs: ["CLAUDE.md", "CLAUDE.local.md (optional)"]
outputs: ["sigma/claude-md-check.md"]
---

# /claude-md-check

Check the project's **CLAUDE.md** (required) and **CLAUDE.local.md** (optional —
skip silently if absent) against the sigma:2026-07-10 best-practice research:
official Anthropic guidance + community consensus + real-world examples
(cloudflare/workers-sdk, vercel/ai, supabase, humanlayer, langchain).

## Deterministic checks (run these yourself, no judgment needed)
1. **Length**: count lines. >300 → HIGH ("over the ceiling where adherence
   measurably degrades"). 200-300 → MEDIUM ("over the official target").
2. **Pasted code blocks**: any fenced code block >15 lines → MEDIUM ("use a
   file:line pointer instead, it will go stale").
3. **`@path` imports**: for each `@path/to/file` NOT inside backticks or a fenced
   block, resolve it relative to the file (per official docs — relative to the
   importing file, not cwd). Broken → HIGH.
4. **Stale test-count claims**: if the file states "N pytest tests", run
   `python3 -m pytest --collect-only -q` and compare. Mismatch → MEDIUM, name
   both numbers.
5. **Placeholders**: any `TODO`/`TBD`/`FIXME` → LOW.

## Qualitative pass (use judgment against the rubric)
Grade the file's actual content, most important first:
1. **Specificity test**: for each instruction, would removing it cause a
   mistake? Flag vague/self-evident lines ("write clean code").
2. **Include/exclude discipline**: flag anything a linter would enforce,
   anything discoverable by reading the code, detailed API docs that should be
   a link, long tutorials.
3. **Imperative voice**: flag hedged language ("we generally prefer X") vs
   direct commands ("use X").
4. **Redundancy/contradiction**: flag repeated or conflicting instructions.
5. **WHAT/WHY/HOW coverage**: does it give tech stack/structure (WHAT), purpose
   (WHY), and workflow/verification steps (HOW) — without over-explaining any one?
6. **Register**: flag README-voice content (narrative history, marketing framing)
   written for humans rather than agent instructions.

Use HIGH only for something that would genuinely mislead every session (a direct
contradiction); most structural/specificity issues are MEDIUM or LOW. If the file
is already good, say so — do not invent findings to seem thorough.

## Report each finding as
```
FINDING | SEVERITY | <file>:<line> | <message>
```

## Gate
FAIL on any CRITICAL/HIGH finding (same law as `/review`). Write the report to
`sigma/claude-md-check.md`.

## Next
- FAIL → prune the flagged lines, then re-run.
- Missing CLAUDE.md entirely → `/claude-md-create --target repo`.
