# Design: Plugin-First Pivot

**Date:** 2026-06-19
**Status:** Approved (all sections)
**Topic:** Re-center sigma as a Claude Code plugin the user carries everywhere
(commands + domain context-as-skill + skills + research style), with a thin
power-CLI for what Claude Code cannot do in-session.

## Motivation

An architecture eval (through the lens "I always work inside Claude Code") found
sigma is two products fighting for one identity:

1. An autonomous external engine (CLI subprocess fan-out, loop, hermes).
2. A Claude Code content pack (commands + 67 domain context-engines + skills).

The user only uses #2. Evidence from the codebase:

- **`cli/worktree.py` is unused scaffolding.** `WorktreeManager` is never imported
  by `loop.py`; the documented "git-worktree isolation for parallel-safe loops"
  does not happen — loop cycles run sequentially in one workspace. (`worktree_name`
  is only an artifact filename.)
- **The 9 domain context-engines are split-brain.** No `cli/*.py` reads
  `context-engines/` (decorative at the CLI level); only `commands/implement-task.md`
  and `commands/tasks.md` tell the agent to read them (live only in plugin mode).
- **CLI stage-wrappers are strictly weaker in-session.** `propose…verify` via CLI
  build a prompt and shell to `claude -p` as an amnesiac subprocess that does NOT
  load domain context. Running `/spec` in-session is better (loads context, steerable).
- **Parallel research is the one irreplaceable CLI power.** `research.py:66` uses
  `ThreadPoolExecutor` to fan out to 3 concurrent `claude`/`gemini`/`codex`
  subprocesses — genuinely impossible in a single Claude session.

## Decisions (locked)

1. **Plugin-first.** The Claude Code plugin (commands + context-engines-as-skill +
   skills + research) is the primary product.
2. **Context-engines → native auto-surfaced skill** (the keystone).
3. **Research: both paths.** Keep the CLI parallel fan-out AND make `/research`
   dispatch Claude Code subagents in-session.
4. **Retire the simple CLI stage subparsers** (`propose/blueprint/spec/tasks/
   implement-task/verify`); those flows live only as plugin slash commands.
5. **Keep `sigma hermes` + `sigma loop` as the CLI autonomous escape hatch.**
   `pipeline.execute_stage` therefore STAYS (hermes/loop call it internally) — only
   the per-stage CLI subparsers + `cmd_stage` are removed.
6. **Delete `cli/worktree.py`** and drop the worktree claim from docs.
7. **Keep** setup (`onboard/doctor/rtk/caveman/secrets/checks`), `board`, `weave`,
   `research`.

## Section 1 — Module fate

| Module / asset | Fate | Why |
|---|---|---|
| `context-engines/` (67 MD) | Promote → native skill (auto-surfaced) | Crown jewel; decorative in CLI, prose-only in plugin |
| `research.py` + `models.py` | Keep | Real ThreadPoolExecutor 3-CLI fan-out |
| `subagents/researchers/` | Activate in `/research` | Authored, unused in-session |
| `commands/*.md` stages | Keep as plugin (primary) | Stage work lives here now |
| CLI stage subparsers + `cmd_stage` | Retire | Strictly weaker than in-session `/stage` |
| `pipeline.execute_stage` + `STAGE_NAMES` | Keep (library) | hermes/loop/board use it |
| `cli/worktree.py` (+ its tests) | Delete + drop doc claim | Unused scaffolding (verified never imported) |
| `sigma hermes`, `sigma loop` | Keep (CLI) | Genuine autonomous escape hatch |
| `onboard/doctor/rtk/caveman/secrets/checks` | Keep | Setup, orthogonal |
| `board.py`, `weave.py` | Keep | Live TUI / artifact tool |

## Section 2 — Context-engines as a native skill (keystone)

New skill `skills/sigma-domains/` that auto-surfaces the right domain guidance.

- **SKILL.md description** lists the 9 domains + trigger keywords so Claude Code
  activates it when a task matches a domain (e.g. "training loop" → deep-learning).
- **Source of truth stays `context-engines/`** (67 files). The skill INDEXES /
  references them — it does not duplicate their content (avoids drift). The skill
  body maps each domain → its `implementers/`, `verifiers/`, `logic-evaluator.md`
  paths and tells the agent to load the relevant file(s) for the task.
- **Maker / checker / logic split preserved:** the skill presents implementer
  guidance, verifier checks, and logic-evaluator as distinct sections, so the
  existing maker≠checker discipline maps onto it.
- A pure index/validator (`cli/domains_index.py`) resolves domain → expected files
  and verifies they exist on disk (like `cli/codetour.py`), so a missing/renamed
  context-engine file is caught by a test, not silently skipped.

## Section 3 — Research rides along (both paths)

- **CLI unchanged:** `sigma research` keeps the `ThreadPoolExecutor` fan-out.
- **Plugin `/research` rebuilt** to dispatch Claude Code subagents (Task/Agent
  fan-out) using `subagents/researchers/` (claude/gemini/gpt personas): true
  in-session parallel research, aggregated + cited, no terminal needed. The
  command body instructs spawning the researcher subagents in parallel and
  synthesizing one cited `research.md`, mirroring the CLI's aggregation contract
  (dedupe, cross-reference, label fact vs inference, list skipped models).

## Section 4 — Deletions + doc truth

- Delete `cli/worktree.py` and any `tests/test_worktree.py`.
- Remove the stage subparsers + `cmd_stage` from `cli/main.py`; keep `research`,
  `loop`, `hermes`, `board`, `weave`, `doctor`, `onboard`, `learn`, `launch`,
  `init`.
- Rewrite `CLAUDE.md`: the "Two ways to run" framing (plugin-first; CLI = research
  + autonomous escape hatch + setup), the Layout (drop worktree, note domains
  skill), Commands (drop per-stage CLI lines), and remove the worktree gotcha.
  Replace with the honest statement that `loop` runs sequential cycles in one
  workspace.

## Section 5 — Testing + docs

- `tests/test_domains_index.py` — pure: every domain resolves to existing
  implementer/verifier/logic-evaluator files; a fake missing file is reported.
- `tests/test_main.py` (or equivalent) — assert retired stage subparsers are gone
  and `research`/`loop`/`hermes`/`board`/`weave` remain.
- Remove dead worktree tests.
- `commands/research.md` — updated body (subagent fan-out) kept lint/structure
  consistent with other command templates.
- All existing tests stay green; ruff clean; Python 3.9-safe types throughout.

## Sequencing (for the plan)

Three largely independent sub-projects, buildable in order:

1. **Cleanup** — delete `worktree.py` + tests, retire stage subparsers, fix docs.
   (Smallest, unblocks a green baseline.)
2. **Domains skill** — `cli/domains_index.py` (pure) + `skills/sigma-domains/SKILL.md`
   indexing the 67 files + tests.
3. **/research subagents** — rebuild `commands/research.md` to dispatch subagents.

## YAGNI / non-goals

- Do NOT wire worktrees (deleting, not fixing).
- Do NOT make the CLI load context-engines (CLI stages are retired; loop/hermes
  keep their string-guidance prompts — unchanged this pass).
- Do NOT duplicate context-engine content into the skill (index/reference only).
- No new runtime dependency. Python 3.9-safe types.
