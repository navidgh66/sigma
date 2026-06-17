# CLAUDE.md — sigma

Guide for AI assistants working in the sigma repo.

## What this is

`sigma` is a personal, portable AI workflow toolkit for data science & AI
engineering. A Python CLI + markdown templates that wrap Claude Code with a
research-first, spec-driven, loop-engineered pipeline. Core and execution are
complete: all 8 stages run through one injectable agent runner; the loop runs
real maker→checker cycles. **Hermes** (optional conductor) routes plain language
to stages; a **kanban board** projects task/event state; the loop adds a second
**logic-evaluator** verify axis. 127 pytest tests, ruff clean.

## Commands

```bash
python3 -m pytest tests/ -q          # run all 127 tests (must stay green)
python3 -m ruff check cli/ tests/    # lint (py39 target)
python3 -m ruff check --fix cli/ tests/

python3 -m cli.main --help           # CLI help
sigma init --domains nlp,rl          # scaffold sigma.config.yml for a project
sigma research "topic"               # multi-model research → research.md
sigma spec --topic <t>               # run one pipeline stage (writes artifact)
sigma spec --topic <t> --dry-run     # print the invocation, don't run claude
sigma loop --topic <t>               # plan cycles (safe default)
sigma loop --topic <t> --execute     # run maker→checker cycles

# Hermes — optional conductor (standalone `sigma <stage>` stays untouched)
sigma hermes "continue" --topic <t>         # route → run ONE stage, then stop
sigma hermes "build it" --topic <t> --auto  # chain stages until a human gate
sigma hermes "..." --topic <t> --terse      # compress output (caveman skill)

# Kanban board — projection over tasks.md + events.jsonl
sigma board --topic <t>              # static snapshot (rich)
sigma board --topic <t> --watch      # live redraw as agents progress
```

## Pipeline

`research → propose → blueprint → spec → tasks → implement-task → verify → loop`

Each stage reads the prior stage's artifact as context. Artifacts live under
`sigma/specs/{YYYY-MM-DD}-{slug}/`.

## Layout

```
cli/__init__.py     __version__
cli/main.py         argparse CLI: init / research / <stages> / loop / launch
cli/config.py       sigma.config.yml load/write/validate + local override merge
cli/paths.py        DOMAINS (9), project root, spec workspace, slugify
cli/models.py       research model adapters (claude/gemini/gpt), graceful skip
cli/research.py     parallel fan-out + cited aggregation → research.md
cli/runner.py       AgentRunner — the single execution chokepoint (injectable)
cli/pipeline.py     execute_stage: run stage, chain prior artifact, persist
cli/loop.py         parse tasks, execute_cycle (maker→checker + logic axis), run_loop
cli/worktree.py     git worktree create/remove for parallel-safe loop isolation
cli/hermes.py       conductor: route → inject skill → execute_stage → emit event
cli/intent.py       hybrid routing: state-scan default + intent-override classify
cli/skill_map.py    stage → bundled skill mapping; inject_skill into prompts
cli/events.py       append/read events.jsonl — append-only board state spine
cli/board.py        kanban projection (pure build_columns) + rich static/live render
cli/keepawake.py    --keep-awake: caffeinate wrapper, prevents Mac sleep on long runs
commands/           8 slash-command templates (one per stage), YAML frontmatter
context-engines/<d>/  9 domains, implementers/ + verifiers/ (each has logic-evaluator.md)
subagents/researchers/  claude / gemini / gpt research subagents
skills/             ratcheted lessons (SKILL.md), written on loop failures
skills/vendor/      bundled skills (superpowers subset + caveman) — self-contained
skills/sigma-present/  skill: export artifacts → single-file HTML deck/report/kanban
installer/setup.sh  one-line global install
.claude-plugin/     plugin.json + marketplace.json — makes sigma a Claude Code plugin
commands/           also serve as native CC slash commands (/research … /hermes /board)
docs/               design doc + roadmap + PLAYGROUND.md (hands-on guide to every feature)
```

## Two ways to run

- **CLI** (`sigma <stage>`) — the full engine: real subprocess model fan-out,
  git-worktree isolation, injectable maker→checker loop. For autonomous runs.
- **Claude Code plugin** — `commands/*.md` are native slash commands (`/research`
  … `/hermes`, `/board`); `skills/sigma-present` is a native skill. Install with
  `/plugin marketplace add navidgh66/sigma` then `/plugin install sigma@sigma`.
  Slash commands are the lightweight in-session flow; they mirror CLI stages 1:1.
  Command bodies carry extra frontmatter (`command:`, `stage:`, `inputs:`) beyond
  CC's required `description:` — harmless, kept for the CLI's own use.

## Principles

- **Loop engineering** — design loops, stay the engineer. Failures ratchet into `skills/`.
- **Maker ≠ checker** — implementer and verifier are always distinct agents. The
  optional logic-evaluator is a third distinct agent (separation enforced).
- **Hermes is additive** — the conductor never replaces standalone `sigma <stage>`
  commands; each stage and bundled skill stays usable on its own.
- **Lean context** — load only the domain a task needs.
- **Multi-model research** — Claude + Gemini + GPT in parallel, aggregated, cited.
- **YAGNI** — no dashboard/telemetry/TS port until the single-user core proves out.

## Conventions

- **Python 3.9** target. Keep type hints 3.9-safe: use `Optional[X]` / `List[X]`
  from `typing`, NOT `X | None` (ruff `UP` rule is intentionally disabled).
- Standard library first; keep the CLI dependency-light (`pyyaml` + `rich`
  runtime — `rich` powers the kanban board only).
- Markdown templates use YAML frontmatter.
- Every research claim is cited; separate fact from inference.

## Gotchas

- `execute_cycle` raises `ValueError` if the same runner instance is passed as
  both maker and checker — separation is enforced, not advisory. Same for the
  logic checker: it must be distinct from both.
- Verdict parsing is skeptical: a checker reply missing `VERDICT: PASS` is
  treated as FAIL. A loop cycle passes only when BOTH the code-quality verifier
  and (if provided) the logic-evaluator pass.
- `sigma loop` plans by default; it only executes cycles with `--execute`.
- `sigma hermes` runs ONE stage by default; `--auto` chains until a human gate
  (spec-approval, verify-failed), a stage failure, or the hop budget (`max_hops`).
- The board is a **pure projection**: it never mutates state. Hermes/loop append
  to `events.jsonl`; `build_columns` folds tasks + latest-event-per-task into
  columns. `events.Event.ts` is passed in by the caller, never generated in the
  projection (keeps it deterministic/testable).
- Pure logic (config, paths, parsing, cycle planning, routing, board projection)
  is separated from subprocess execution so everything is testable with fakes.
- All agent/model invocation passes the prompt via argv (never the shell) — no
  injection risk; preserve that when adding adapters.
- `skills/vendor/` are unmodified upstream copies — don't edit in place; re-vendor.
- `--keep-awake` (loop/hermes) wraps macOS `caffeinate` via `cli/keepawake.py`. It
  no-ops off macOS or when caffeinate is absent, and is torn down on context exit
  (even on exception) — best-effort, never fatal.
