---
command: /loop
description: Run every open task in tasks.md to done in this session. Distinct implementer and verifier agents per task, test tamper guard, BDD e2e check, capped retries, lessons ratcheted on failure. A Stop hook keeps the run going until tasks settle.
stage: 8
inputs: ["sigma/specs/{date}-{slug}/tasks.md", "sigma/specs/{date}-{slug}/spec.md"]
outputs: ["implementations", "sigma/specs/{date}-{slug}/loop-state.json", "skills/<lesson>/SKILL.md on failure"]
---

# /loop

Design the loop, stay the engineer. This command runs unattended: it keeps going until
every task has passed or failed, or something genuinely needs the user.

## 1. Start

1. Find the project root (`git rev-parse --show-toplevel`, else the current directory;
   call it `<root>`) and the workspace (`<root>/sigma/specs/{date}-{slug}/`, newest
   unless the user names one). Read `tasks.md` and `spec.md`.
2. Write `loop-state.json` in the workspace (JSON, so it is not rewritten casually):

   ```json
   {"version": 1, "status": "running", "topic": "<workspace name>",
    "started_at": "<UTC ISO time>", "budget_seconds": null,
    "max_nudges": 3, "nudges": 0, "nudge_open_count": null, "blocker": null,
    "tasks": [{"id": "T1", "title": "...", "domain": "nlp", "scenario": null,
               "status": "open", "attempts": 0, "note": ""}]}
   ```

   One entry per unchecked task line. `scenario` comes from a `[scenario: <name>]` tag.
   Respect `loop.max_cycles` in `sigma.config.yml` as the most tasks this run takes on;
   leave the rest out and say so. If the user gives a time budget, set `budget_seconds`.
3. You are the only writer of this file. Update it after every step below. The plugin's
   Stop hook reads it: while tasks are open and `blocker` is empty, it sends you back to
   work (at most 3 times without progress).

## 2. Per task (in order)

Say one line of intent before each task, and a one-line result after it.

1. Set the task `in_progress`. Recall up to 5 lessons for its domain (the `sigma-lessons`
   skill, newest first).
2. Snapshot the tests:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_guard.py" snapshot <workspace>/.test-snapshot-<id>.json --root <root>`
3. Test-first, only if the user asked for TDD: dispatch `sigma-test-writer`, then take
   the snapshot again so its new test is protected too.
4. Dispatch `sigma-implementer` with: the task line, domain, the scenario text from
   spec.md, the failing test path (TDD), the lessons, and the verifier's findings from
   the previous attempt if this is a retry. Point it at `ARCHITECTURE.md` if present.
5. Tamper check:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_guard.py" check <workspace>/.test-snapshot-<id>.json --root <root>`
   Exit 1 means the implementer edited or deleted existing tests: the attempt fails with
   the listed paths as the reason (the verifier is skipped).
6. Dispatch `sigma-verifier` (fresh context) with the task, domain, scenario, the changed
   files, and the lessons. No `VERDICT: PASS` line means FAIL.
7. If verify passed and the task has a scenario: dispatch `sigma-e2e` with the scenario.
   FAIL fails the attempt. ERROR is an environment problem: note it on the task and
   do not fail the attempt for it. No verdict line means ERROR.
8. Pass: status `passed`, and tick the task's line in `tasks.md` (`- [ ]` to `- [x]`)
   so a later run does not redo it. Fail: `attempts += 1`; if `attempts < 3`, retry from step 4
   with the failure findings; otherwise status `failed` and ratchet a lesson (below),
   then move to the next task.

Parallel, only when the user asks ("in parallel", "as a team"):

- Pick tasks that touch different files; tasks that share files run one after another.
- Set `budget_seconds` (the user's figure, else 1800) and put `elapsed Ns / Bs` in each
  brief and in your own status lines.
- Dispatch one `sigma-implementer` per task in a single message with
  `isolation: worktree`. Each worktree is that task's `<root>` for steps 2 to 7: take
  the snapshot there before dispatch, and run the tamper check, `sigma-verifier` and
  `sigma-e2e` against that worktree path.
- A passing task's worktree branch is merged back into the branch the loop started on
  before it is marked `passed`. A merge conflict: leave the worktree in place, set the
  task `blocked` with the conflict in `note`, and continue with the others.
- Wait for every dispatched agent before ending a turn.

## 3. Lessons (on a failed task)

First check for an existing lesson on the same topic in the same domain (the way
`/sigma-learn-lesson` does). Never overwrite one: if `skills/<slug>/` already exists, use
`skills/<slug>-2/` (then `-3`, ...), add a `> ⚠ CONTRADICTION: may conflict with
<existing path>` line to the new lesson, and append the pair to
`skills/CONTRADICTIONS.md`. Then write the lesson in the ratchet format:

```markdown
---
name: <slug of "loop failed: <task title>">
description: Avoid recurrence of: loop failed: <task title>
metadata:
  domain: <domain>
  created: <YYYY-MM-DD>
---

# loop failed: <task title>

**What failed:** <one line>

**Lesson (ratcheted):** <the rule that would have prevented it>

**How to apply:** Check this before implementing similar work in the `<domain>` domain.
```

## 4. Finish

When no task is `open` or `in_progress`: set `status` to `done`, delete the
`.test-snapshot-*.json` files, and give the recap: passed, failed (with the reason),
lessons written, tasks left out by the cap. Suggest `/simplify` for a cleanup pass and
`/review` before merging.

## When to stop, and when not to

A standing instruction from the user, the person you are working for. It is about how your turns end. A message with no tool call in it ends your turn, and the work stops there until you are asked to continue. The user has seen you end turns in four ways while work they asked for was still owed, and does not want any of them. One: a long summary of what was done that closes by announcing the next step and has no tool call, so the next thing never starts. Two: an offer to carry on with something unless the user would prefer otherwise, which stops to wait for an answer the user was not going to give. Three: a list of decisions for the user when, by your own account, none of them blocks the rest of the work. Four: deciding that this is a good place to report, because the turn has been long or a milestone is done. Status notes are welcome, and so are your recommendations on open decisions, but put them in the same message as your next tool call and carry on with whatever does not depend on the user's answer. If you notice yourself inviting the user to redirect you or offering to wait, delete it and do the next thing. The stops the user does want are the ones where nothing can move without them, or where the thing blocking you is deliberately protected from you. This does not override the need for confirmation on risky or destructive actions.

In this loop, "nothing can move without them" means: set `blocker` in `loop-state.json`
to what you need, then stop.

## Guardrails

- Maker and checker are different agents; the verifier has no edit tools.
- Existing tests are protected by the tamper guard.
- The Stop hook caps automatic continuations at 3 without progress.
- Markdown and JSON in the workspace are the memory across turns.
