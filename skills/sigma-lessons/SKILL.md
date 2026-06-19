---
name: sigma-lessons
description: >
  Recall sigma's past ratcheted lessons before implementing or verifying a task,
  so previous mistakes are not repeated. Use when about to write or review code in
  any sigma domain (classic-ml, deep-learning, nlp, rl, data-analysis,
  data-engineering, ai-agent-engineering, mlops, llm-engineering), when starting a
  loop task, or when the user asks "what have we learned" / "avoid past mistakes".
  Lessons are written by the loop on failure and by /sigma-learn-lesson; this skill
  reads them back.
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
2. **Read the lessons for that domain:** scan `skills/**/SKILL.md` for files whose
   frontmatter `domain:` matches. Each has a `**Lesson (ratcheted):**` line and a
   `**How to apply:**` line — those are the actionable parts.
3. **Apply them** as constraints while implementing or as extra checks while
   verifying. Treat a lesson as "do not repeat this mistake."
4. If a lesson looks stale or wrong, do NOT silently delete it — flag it for the
   human (sigma never auto-resolves lessons; see `skills/CONTRADICTIONS.md`).

## Notes

- The CLI loop does this automatically (`cli/skills_recall.py` builds the recall
  block and injects it into the implement + verify prompts). This skill is the
  in-session equivalent for slash-command work.
- Lessons without a `domain:` (vendor skills, sigma-present, sigma-domains) are
  NOT lessons — ignore them here.
