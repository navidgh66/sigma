---
command: /sigma-learn-lesson
description: Capture a lesson from the current session into sigma's ratcheted skills (contradiction-safe)
stage: learn-lesson
inputs: []
outputs: ["skills/<slug>/SKILL.md"]
---

# /sigma-learn-lesson

Capture a mistake from **this session** as a durable lesson, so future sigma runs
(loop cycles + in-session work) recall it and avoid repeating it. This is the
manual, outside-the-loop path to the same learning store the loop writes to.

## When to use

The human says "learn from this mistake", "remember this", "don't do that again",
or invokes `/sigma-learn-lesson`.

## Behavior

1. **Review the current session** and extract:
   - **mistake** — what went wrong (one line).
   - **lesson** — the rule to apply next time (actionable, specific).
   - **domain** — the best-fit sigma domain: `classic-ml`, `deep-learning`,
     `nlp`, `rl`, `data-analysis`, `data-engineering`, `ai-agent-engineering`,
     `mlops`, `llm-engineering`, or `general` if none fits.
2. **Pick a topic** — a short noun phrase naming what the lesson is about (e.g.
   "tokenize corpus"). The skill title is `session lesson: <topic>`.
3. **Check for contradictions** — scan `skills/**/SKILL.md` for an existing lesson
   with the SAME domain + same topic (the `session lesson:` / `verify failed:`
   prefix is ignored when matching). If one exists and disagrees, do NOT delete or
   overwrite it — add a `⚠ CONTRADICTION` marker and a line to
   `skills/CONTRADICTIONS.md`. Humans decide.
4. **Write** `skills/<slug>/SKILL.md` where `<slug>` is the kebab-cased title,
   using exactly this format (matches the loop's ratchet so recall finds it):

   ```markdown
   ---
   name: session-lesson-<topic-slug>
   description: Avoid recurrence of: session lesson: <topic>
   metadata:
     domain: <domain>
   ---

   # session lesson: <topic>

   **What failed:** <mistake>

   **Lesson (ratcheted):** <lesson>

   **How to apply:** Check this before implementing similar work in the `<domain>` domain.
   ```

5. **Confirm** the written path and report any contradiction flagged.

## Rules

- Use the EXACT format above — the `metadata: domain:` tag and the
  `**Lesson (ratcheted):**` / `**How to apply:**` lines are what `skills_recall`
  reads back. A lesson missing the domain tag will never be recalled.
- One lesson per invocation; keep it specific and actionable.
- Never delete or rewrite an existing lesson — flag contradictions for the human.

## Next

→ the lesson is now recalled automatically on the next `sigma loop` cycle in that
domain, and via the `sigma-lessons` skill in-session.
