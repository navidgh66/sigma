# In-session loop + Opus 5.5 refresh + feature cut (0.28.0)

Status: approved in brainstorming 2026-09-24, pending written-spec review.

## 1. Why

- The owner uses the **in-session pipeline** and **setup/hygiene** tools. The CLI
  autonomous engine (`sigma loop`, `hermes`, `board`, `weave`) and several quality
  tools (`eval`, `lessons`, `trajectory`) are unused, yet hold most of sigma's code
  and most of CLAUDE.md.
- sigma's real loop engineering lives in the CLI `loop.py` (1166 lines, 7 roles),
  while the in-session `/loop` is a 74-line prompt. The loop the owner actually runs
  is the weakest one.
- The Opus 5.5 prompting guide
  (https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)
  gives concrete harness patterns for unattended runs, effort, time signals, progress
  updates and pasted content. sigma should use them.
- 2025-26 research argues against bloat: long context files raise cost ~20% with
  little gain (arXiv 2602.11988); big skill libraries hurt selection (arXiv 2605.24050);
  checkers that cannot run code can make good drafts worse (arXiv 2607.21656); coding
  agents edit tests to pass even when told not to (ImpossibleBench, arXiv 2510.20270).

## 2. Success criteria

1. `/loop` runs every open task to done in one session without stopping early, and
   stops only on: all tasks passed/failed, a recorded blocker, a risky action needing
   confirmation, or 3 unproductive nudges.
2. Maker and checker are separated by **tool permissions**, not only by prompt text:
   the verifier agent has no Edit/Write tools.
3. A task whose implementer edited test files fails verification.
4. The removal list in section 5 is gone, with no dangling imports, commands, docs or
   tests. `/review` still ratchets lessons.
5. CLAUDE.md is under 200 lines.
6. `pytest`, `ruff check cli/ tests/ hooks/`, and `sigma docs-check --check` pass.

## 3. The new in-session `/loop`

### 3.1 Roles (plugin `agents/*.md`)

The plugin gains an `agents/` directory. Each role is a subagent with its own `effort`
and `tools` frontmatter. Per the 5.5 guide, effort is the main control and starts at
`medium`; `xhigh`/`max` are reserved for measured gains.

| Agent file | Role | effort | tools |
|---|---|---|---|
| `agents/sigma-implementer.md` | Implements one task. Gets task, domain, mapped scenario, recalled lessons, ARCHITECTURE.md pointer. | medium | all (default) |
| `agents/sigma-verifier.md` | Independent checker. Merges today's code-quality verifier and logic evaluator. Must run the tests/build itself and quote evidence (command + output, `file:line`) before `VERDICT: PASS` or `VERDICT: FAIL`. | medium | Read, Grep, Glob, Bash (no Edit, Write, NotebookEdit) |
| `agents/sigma-test-writer.md` | TDD only (user asks for test-first). Writes a failing test from the task's BDD scenario. | low | Read, Grep, Glob, Write, Edit, Bash |
| `agents/sigma-e2e.md` | Only when the task has `[scenario: <name>]`. Drives Given/When live, checks Then. Verdict `PASS`/`FAIL`/`ERROR` (ERROR never gates, as today). | low | Read, Grep, Glob, Bash |

Dropped roles: **advisor** (a failed check instead gives the implementer the verifier's
findings for a retry) and **simplifier** (Claude Code's built-in `/simplify` covers it;
`/loop` may suggest it in the final recap).

Prompt rules for all four agents (5.5 guide):
- No "think carefully" / "think step by step" lines; effort frontmatter does that job.
- Never ask for reasoning written out in the response (risk of `reasoning_extraction`
  refusals). Ask for **evidence** instead.
- Plain wording; no stacked MUST/NEVER capitals.

### 3.2 State file: `loop-state.json`

Lives in the spec workspace: `sigma/specs/{date}-{slug}/loop-state.json`. JSON, not
markdown, because agents overwrite JSON less readily. `/loop` creates it from `tasks.md`
at start and is the only writer during the run (subagents report back; the lead
updates the file).

```json
{
  "version": 1,
  "status": "running",
  "topic": "2026-09-24-example",
  "started_at": "2026-09-24T10:00:00Z",
  "budget_seconds": null,
  "max_nudges": 3,
  "nudges": 0,
  "nudge_open_count": null,
  "blocker": null,
  "tasks": [
    {"id": "T1", "title": "...", "domain": "nlp", "scenario": null,
     "status": "open", "attempts": 0, "note": ""}
  ]
}
```

- `status` (run): `running` | `done` | `stopped`.
- task `status`: `open` | `in_progress` | `passed` | `failed` | `blocked`.
- `blocker`: free text; when set, the run may stop and the text is surfaced to the user.
- `budget_seconds`: optional; set when the user gives a time budget or runs parallel mode.

### 3.3 Per-task cycle

1. Pick the next `open` task; set it `in_progress`; say one line of intent
   (5.5: predictable progress updates).
2. Record the test-file baseline: `git diff --name-only` + untracked files matching test
   paths (`tests/`, `test_*.py`, `*_test.py`, `*.test.*`, `*.spec.*`).
3. TDD mode only: dispatch `sigma-test-writer`; its test files join the baseline as
   **protected**.
4. Dispatch `sigma-implementer`.
5. **Tamper guard:** if the implementer changed any protected test file, or deleted/
   edited any pre-existing test file, the attempt fails with reason "implementer edited
   tests: <paths>". New test files the implementer adds are allowed.
6. Dispatch `sigma-verifier` (fresh context, the diff + task + scenario + domain
   verifier and logic-evaluator checklists). Skeptical parse: no `VERDICT: PASS` line
   means FAIL.
7. If verify passed and the task maps a scenario: dispatch `sigma-e2e`. FAIL gates;
   ERROR is noted only.
8. Pass: task `passed`. Fail: `attempts += 1`; if `attempts < 3`, re-dispatch the
   implementer with the verifier's findings (at most 2 retries); else task `failed`,
   ratchet a lesson (3.6), continue with the next task.
9. One-line recap per task (passed/failed and why).

After the last task: set run `status` to `done`, give the final recap (what passed,
what failed and why, lessons ratcheted, suggestion to run `/simplify` or `/review`).

### 3.4 Stop hook: `hooks/loop_guard.py`

Plugin-level hook, registered in `hooks/hooks.json`:

```json
{"hooks": {"Stop": [{"hooks": [{"type": "command",
  "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/loop_guard.py\""}]}]}}
```

Pure stdlib, Python 3.9, self-contained (the plugin checkout is separate from the CLI
checkout, so it must not import `cli.*`). Split into a pure `decide(state, hook_input,
now) -> Decision` plus a thin `main()` that reads stdin, finds the state, writes back
the counters, and prints the result.

Finding the state: newest `sigma/specs/*/loop-state.json` under the hook input's `cwd`
whose `status == "running"`.

Decision rules, in order:
1. No running state, unreadable file, or bad JSON: **allow** (exit 0, no output).
   A broken guard must never trap a session.
2. `blocker` is set: **allow**.
3. No task is `open`/`in_progress`: **allow**.
4. Nudge accounting: if the count of open tasks is lower than `nudge_open_count`
   (progress was made), reset `nudges` to 0. If `nudges >= max_nudges`: set run
   `status = "stopped"`, **allow** (a stuck run ends and can be reviewed).
5. Otherwise **block**: increment `nudges`, store `nudge_open_count`, print
   `{"decision": "block", "reason": "<nudge>"}`.

Nudge text (adapted from the 5.5 guide's example):

> Your loop still has open tasks: T3 (add tokenizer cache), T5 (eval split). Continue
> with them. If one is blocked, set `blocker` in loop-state.json and say what blocks it.
> (elapsed 340s / 1200s)

The elapsed part appears only when `budget_seconds` is set (5.5: time signals); without
a budget it shows `elapsed 340s`.

Claude Code also force-ends a turn after 8 consecutive Stop blocks, so the cap of 3 is
well inside that.

Background work: the 5.5 guide says a still-running subagent or command means the task
is not done. `/loop` dispatches its subagents in the foreground and waits for them, so
the guard does not need to inspect background tasks. Parallel mode (3.5) waits for all
dispatched agents before the turn can end.

### 3.5 Parallel mode (opt-in)

Only when the user asks ("in parallel", "as a team"). Independent tasks (no shared
files) are dispatched to `sigma-implementer` in one message with `isolation: worktree`.
The lead sets `budget_seconds` (user-given or a default of 1800) and includes
`elapsed Ns / Bs` in each subagent brief and in its own status lines (5.5: time signals
for multiagent harnesses). Tasks that touch the same files run serially.

### 3.6 Lessons (auto-ratchet, capped recall)

- A task that ends `failed` ratchets a lesson into `skills/<slug>/SKILL.md` in the
  existing format (same as `/sigma-learn-lesson`), with a new `metadata.created:
  YYYY-MM-DD` field. Contradiction flagging unchanged.
- Recall is capped at **5 per domain, newest first** by `metadata.created`; lessons
  without it sort after dated ones, ties by path (deterministic). Applies to
  `cli/skills_recall.py` (`DEFAULT_LIMIT` 12 → 5, new ordering) and to the
  `sigma-lessons` skill text.

### 3.7 `commands/loop.md` and `commands/implement-task.md`

- `loop.md` is rewritten around 3.1 to 3.6. It ends with the 5.5 guide's unattended-run
  paragraph (the four unwanted early stops), adapted: status notes go with the next
  tool call; the wanted stops are "a recorded blocker" and "a risky or destructive
  action that needs the user's confirmation".
- `implement-task.md` stays the single-task, human-in-the-loop entry point. It points at
  the same agents and tamper guard, and does **not** carry the unattended paragraph
  (5.5: leave it out of human-in-the-loop flows).

## 4. Opus 5.5 refresh elsewhere

- **Pasted and outside content** (5.5: mark pasted text): `/craft` accepts pasted
  designs and treats them as data wrapped in `<pasted_content id="...">` tags;
  `/research` (manual findings, web results) and `/review` (other people's diffs)
  treat outside text as data. All three follow instructions inside such text only
  where the user's own message asks. (The `claude-md` commands were first listed here
  by mistake: they check for pasted code *in* CLAUDE.md and take no pasted input.)
- **Tone:** the 26 capitalized MUST/NEVER/ALWAYS/CRITICAL/IMPORTANT/DO NOT words across
  `commands/` and `skills/sigma-*` are rewritten in plain wording, keeping at most one
  emphasized line per file where it guards a real hazard.
- **Domain knowledge for AI engineers:**
  - `context-engines/llm-engineering/implementers/prompt-engineering.md`: replace the
    "Think step by step" advice with Claude 5 family guidance: effort as the main
    thinking control (start `medium`), no reasoning-in-response prompts
    (`reasoning_extraction`), `max_tokens` headroom for thinking (up to 128k for long
    agentic turns), read responses by block type, mark pasted content.
  - `context-engines/ai-agent-engineering/`: add harness patterns: text-only end of
    turn is a report; checklist + capped continuations (2-3); name the unwanted early
    stops; small-model completion check; time-budget line for agent teams; progress
    updates via `thinking.display: "updates"`.
  - The matching `verifiers/` and `logic-evaluator.md` get the checks that mirror those
    patterns (for example, flag an agent loop that treats `end_turn` as done).

## 5. Removals

CLI subcommands and flags:
- `sigma loop`, `sigma hermes`, `sigma board`, `sigma weave`, `sigma eval`,
  `sigma lessons`, `sigma trajectory`, `sigma launch`.

Modules (and their tests):
- `cli/loop.py`, `hermes.py`, `pipeline.py`, `intent.py`, `events.py`, `board.py`,
  `weave.py`, `weave_manifest.py`, `gate.py`, `keepawake.py`, `worktree.py`,
  `eval.py`, `eval_run.py`, `lessons.py`, `trajectory.py`, `axis_economy.py`,
  `telemetry.py`, `scenarios.py`.
- `AgentRunner`: drop the `telemetry`, `trajectory_sink`, `argv_builder` and
  `output_cleaner` params, and `cli/models.py`'s `codex_argv_builder` (only
  loop/hermes/eval used them). Keep `model` (small, generic seam).
- `cli/cost.py`: drop loop/hermes/eval routing entries; keep review/profile/research.
- `cli/skill_map.py`: drop stages that no longer exist; keep what `learn.py` uses.
- `cli/checks.py`, `cli/doctor.py`, `cli/onboard.py`, `cli/uninstall.py`,
  `installer/setup.sh`: drop references to removed features.

Plugin surface:
- `commands/hermes.md`, `board.md`, `weave.md`, `eval.md`.
- `sigma/evals/` (sample set).
- `skills/sigma-present`: drop the kanban-board mode (the board is gone).
- `.claude-plugin/plugin.json` description: drop Hermes/kanban/HTML chain wording.

Refactor to keep `/review` working:
- New `cli/ratchet.py` holds `render_skill`, `ratchet_to_skills`, `flag_contradiction`
  (moved from `loop.py`, behavior unchanged plus `created`). `review_run.py` imports it.

Docs:
- CLAUDE.md rewritten to under 200 lines: what sigma is, commands, layout, the loop
  contract, and only the gotchas for code that still exists.
- README.md and `docs/PLAYGROUND.md` trimmed to the kept surface.
- ARCHITECTURE.md regenerated or hand-edited to match.
- Old design docs under `docs/superpowers/` stay as history.

## 6. Error handling

- Stop hook: fail open on every error path (rule 1). Never raises; `main()` catches all
  exceptions and exits 0 with no output.
- Hook write-back failure (read-only FS): allow the stop. The nudge counter could not
  advance, so blocking would risk repeating past the cap (fail open).
- Invalid or non-object hook input on stdin: allow the stop (fail open).
- Verifier output without a verdict line: FAIL (skeptical, as today).
- e2e output without a verdict line: ERROR (inconclusive, never gates, as today).
- Tamper guard outside a git repo: skip the guard and note it in the task `note`.

## 7. Testing

- `tests/test_loop_guard.py`: `decide()` covers allow-no-state, allow-bad-json,
  allow-blocker, allow-all-done, block-open-tasks (reason names ids and titles),
  cap-reached-stops-and-sets-status, nudge-reset-on-progress, elapsed text with and
  without budget. `main()` smoke test with stdin JSON and a temp workspace; exits 0 on
  garbage stdin.
- `tests/test_plugin_agents.py`: each `agents/*.md` has valid frontmatter with `name`,
  `description`, `effort`; verifier `tools` excludes Edit/Write/NotebookEdit;
  `hooks/hooks.json` parses and references `loop_guard.py`.
- `tests/test_ratchet.py`: moved ratchet tests plus `created` rendering.
- `tests/test_skills_recall.py`: cap of 5, newest-first ordering, undated after dated.
- `tests/test_prompts_opus55.py`: no command/agent/skill file contains "think step by
  step" / "think carefully" / "explain your reasoning"; `loop.md` contains the
  unattended paragraph and `implement-task.md` does not.
- Remove tests for deleted modules. Run `pytest`, `ruff`, `sigma docs-check --check`.

## 8. Release

- Version 0.28.0 in `cli/__init__.py` and `.claude-plugin/plugin.json`, in the same
  change as the README and CLAUDE.md updates (release checklist).
- Branch `claude/sleepy-shannon-rg3499`.

## 9. Out of scope

- Human approval gate for lessons (owner chose auto + cap).
- Property-based or mutation testing, eval-judge calibration, ML experiment keep/revert
  loop (research ideas worth a later spec).
- Changes to `/research`, `/grill`, `/grill-loop`, `/review` logic beyond the prompt
  refresh in section 4.
