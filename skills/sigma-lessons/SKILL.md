---
name: sigma-lessons
description: >
  Recall sigma's past ratcheted lessons before implementing or verifying a task,
  so previous mistakes are not repeated. Use when about to write or review code in
  any sigma domain (classic-ml, deep-learning, nlp, rl, data-analysis,
  data-engineering, ai-agent-engineering, mlops, llm-engineering), when starting a
  loop task, or when the user asks "what have we learned" / "avoid past mistakes".
  Lessons are written by /loop on failure, by sigma review, and by
  /sigma-learn-lesson; this skill reads back the 5 newest.
origin: sigma
---

# sigma-lessons

sigma accumulates lessons from failures (the loop ratchets them) and from the
human (`/sigma-learn-lesson`). Each lesson is a `skills/<slug>/SKILL.md` tagged
with `metadata: domain:`. This skill **reads them back** so a future task applies
them instead of repeating the mistake.

## When to use

- Before implementing or verifying a task in a known domain — pull the lessons
  for that domain first.
- When the user asks to recall what was learned, or to avoid prior mistakes.

## Workflow

1. **Identify the domain** of the current task (one of the 9 sigma domains; if a
   task line is annotated `(domain)`, use that).
2. **Read the lessons for that domain:** scan `skills/**/SKILL.md` (skip
   `skills/archive/`) for files whose frontmatter `domain:` matches. Keep at most
   **5**, newest first by `metadata.created` (lessons without a date come last).
   Each has a `**Lesson (ratcheted):**` line and a `**How to apply:**` line; those
   are the actionable parts.
3. **Apply them** as constraints while implementing or as extra checks while
   verifying. Treat a lesson as "do not repeat this mistake."
4. If a lesson looks stale or wrong, flag it for the human instead of deleting it
   (sigma never auto-resolves lessons; see `skills/CONTRADICTIONS.md`).

## Notes

- The cap is small on purpose: big skill libraries measurably hurt agents (they
  pick the wrong lesson), so the few most recent lessons win. `/loop` passes these
  to its implementer and verifier; `sigma review` uses the same rule via
  `cli/skills_recall.py`.
- Lessons without a `domain:` (vendor skills, sigma-present, sigma-domains) are not
  lessons; ignore them here.
