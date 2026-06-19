# CLAUDE.md — sigma

Guide for AI assistants working in the sigma repo.

## What this is

`sigma` is a personal, portable AI workflow toolkit for data science & AI
engineering — **plugin-first**: a Claude Code plugin (commands + domain
context-engines as skills + skills) you carry into any repo, backed by a thin CLI
for what Claude Code can't do in-session. Research-first, spec-driven,
loop-engineered pipeline. Stages run in-session as slash commands; the CLI keeps
parallel `research`, the autonomous `loop`/`hermes` escape hatch, `board`,
`weave`, and setup. **Hermes** routes plain language to stages; a **kanban board**
projects task/event state; the loop adds a **logic-evaluator** verify axis and a
**closed learning loop** (failures + `/sigma-learn-lesson` ratchet into `skills/`
and are recalled by domain on the next run). 321 pytest tests, ruff clean.

## Commands

```bash
python3 -m pytest tests/ -q          # run all 321 tests (must stay green)
python3 -m ruff check cli/ tests/    # lint (py39 target)
python3 -m ruff check --fix cli/ tests/

python3 -m cli.main --help           # CLI help
sigma init --domains nlp,rl          # scaffold sigma.config.yml for a project
sigma research "topic"               # multi-model research → research.md
sigma research "topic" --deep        # web-grounded deep research (web search; slower)
sigma learn                          # learn the codebase → ARCHITECTURE.md + .tours/<slug>.tour
sigma learn --persona "new dev" --dry-run  # print the invocation, don't run claude
# Pipeline stages (propose..verify) run IN-SESSION as plugin slash commands
# (/propose .. /verify). They are NOT standalone CLI subcommands — running a
# stage in Claude Code loads the domain context-engine and is steerable; an
# amnesiac `claude -p` subprocess is strictly weaker. See "Two ways to run".

sigma loop --topic <t>               # plan cycles (safe default; autonomous escape hatch)
sigma loop --topic <t> --execute     # run maker→checker cycles

# Hermes — autonomous CLI conductor (escape hatch for hands-off runs)
sigma hermes "continue" --topic <t>         # route → run ONE stage, then stop
sigma hermes "build it" --topic <t> --auto  # chain stages until a human gate
sigma hermes "..." --topic <t> --terse      # compress output (caveman skill)

# Kanban board — projection over tasks.md + events.jsonl
sigma board --topic <t>              # static snapshot (rich)
sigma board --topic <t> --watch      # live redraw as agents progress

# Weave — stage artifacts → one self-contained HTML chain + machine manifest
sigma weave --topic <t>              # → chain.html (human) + chain.json (machine)
sigma weave --topic <t> --dry-run    # print the invocation, don't run claude

# Setup & health
sigma onboard                        # friendly first-run: domains, API keys, RTK
sigma doctor                         # diagnose + confirm-gated fixes
sigma doctor --check                 # read-only, exit 1 on any failure (CI)
sigma doctor --yes                   # apply all fixes without prompting
sigma doctor --update                # pull sigma + re-vendor before checking
```

## Pipeline

`research → propose → blueprint → spec → tasks → implement-task → verify → loop`

Each stage reads the prior stage's artifact as context. Artifacts live under
`sigma/specs/{YYYY-MM-DD}-{slug}/`.

## Layout

```
cli/__init__.py     __version__
cli/main.py         argparse CLI: init / research / loop / hermes / board / weave / doctor / onboard / learn / launch (pipeline stages are plugin-only)
cli/config.py       sigma.config.yml load/write/validate + local override merge
cli/paths.py        DOMAINS (9), project root, spec workspace, slugify
cli/models.py       research adapters (claude -p / gemini -p --json / gpt via codex exec); clean_output; deep_args
cli/research.py     parallel fan-out + cited aggregation → research.md; --deep web-grounded brief
cli/learn.py        sigma learn — agent-driven codebase walkthrough → ARCHITECTURE.md + .tours/<slug>.tour
cli/codetour.py     pure CodeTour .tour validator (file exists / line in range / pattern present)
cli/runner.py       AgentRunner — the single execution chokepoint (injectable)
cli/pipeline.py     execute_stage library (used by hermes/loop): run stage, chain prior artifact, persist; verify reads full chain via chain.json
cli/weave.py        sigma weave — agent-driven: stage artifacts → chain.html (manifest written first, agent-independent)
cli/weave_manifest.py  pure: build_manifest → chain.json contract + validate_chain_html guard
cli/domains_index.py  pure: resolve each domain → implementer/verifier/logic-evaluator files; powers skills/sigma-domains
cli/loop.py         parse tasks, execute_cycle (maker→checker + logic axis), run_loop (sequential, one workspace)
cli/hermes.py       conductor: route → inject skill → execute_stage → emit event
cli/intent.py       hybrid routing: state-scan default + intent-override classify
cli/skill_map.py    stage → bundled skill mapping; inject_skill into prompts
cli/events.py       append/read events.jsonl — append-only board state spine
cli/board.py        kanban projection (pure build_columns) + rich static/live render
cli/keepawake.py    --keep-awake: caffeinate wrapper, prevents Mac sleep on long runs
cli/checks.py       pure diagnostic probes (python/deps/models/secrets/skills/plugin/config/workspaces/rtk/caveman)
cli/doctor.py       sigma doctor — run checks, confirm-gated fixes, --check/--yes/--update
cli/onboard.py      sigma onboard — first-run setup: domains, API keys, sign-in guide, RTK, caveman
cli/secrets.py      ~/.sigma/.env key store (chmod 600) — never the committed config
cli/rtk.py          detect/install/activate RTK token-saver (confirm-gated, idempotent)
cli/caveman.py      detect/install caveman terse-output mode (confirm-gated, RTK-shaped)
cli/render.py       σ logo + rich/plain check output + confirm prompt
cli/gate.py         wakeAgent gate — cheap pluggable pre-check, skip work (0 tokens)
cli/skills_index.py topic-key + contradiction detection across ratcheted skills
cli/skills_recall.py  pure: recall_lessons(skills_dir, domain) + render_recall_block — read side that closes the learning loop
commands/           slash-command templates (one per stage + /learn + /weave + /sigma-learn-lesson), YAML frontmatter
context-engines/<d>/  9 domains, implementers/ + verifiers/ (each has logic-evaluator.md) — surfaced in-session via skills/sigma-domains
subagents/researchers/  claude / gemini / gpt research subagents (CLI fan-out + /research in-session)
skills/             ratcheted lessons (SKILL.md): written on loop failures + by /sigma-learn-lesson; recalled by domain next run
skills/vendor/      bundled skills (superpowers subset + caveman + code-tour + codebase-onboarding) — self-contained
skills/sigma-present/  skill: export artifacts → single-file HTML deck/report/kanban
skills/sigma-domains/  skill: auto-surface the right domain context-engine (indexes context-engines/, no duplication)
skills/sigma-lessons/  skill: recall past ratcheted lessons by domain in-session (read side of the loop)
installer/setup.sh  one-line install: CLI + deps + plugin auto-register + RTK (TTY-safe)
.claude-plugin/     plugin.json + marketplace.json — makes sigma a Claude Code plugin
docs/               design doc + roadmap + PLAYGROUND.md (hands-on guide to every feature)
```

## Two ways to run (plugin-first)

sigma is **plugin-first**: a Claude Code plugin you carry everywhere. The CLI
keeps only what Claude Code cannot do in-session, plus setup.

- **Claude Code plugin (primary)** — `commands/*.md` are native slash commands
  (`/research`, `/propose` … `/verify`, `/hermes`, `/board`, `/weave`, `/learn`);
  `skills/sigma-present` + `skills/sigma-domains` are native skills (the latter
  auto-surfaces the right domain context-engine). Install with
  `/plugin marketplace add navidgh66/sigma` then `/plugin install sigma@sigma`.
  The pipeline **stages run here** — in-session they load the domain context and
  are steerable. Command bodies carry extra frontmatter (`command:`, `stage:`,
  `inputs:`) beyond CC's required `description:` — harmless.
- **CLI (power tools + escape hatch)** — only:
  - `sigma research` — real parallel multi-model fan-out (ThreadPoolExecutor →
    concurrent claude/gemini/codex subprocesses; impossible in one session).
  - `sigma loop` / `sigma hermes` — autonomous, hands-off runs (sequential cycles
    in one workspace; auto-chain + ratchet). The escape hatch when you want to
    walk away, even though most work happens in-session.
  - `sigma board` / `sigma weave` — live TUI projection / HTML artifact chain.
  - setup: `onboard`, `doctor`, `rtk`, `caveman`.
  The per-stage CLI wrappers (`sigma spec` …) were **retired** — those flows are
  plugin slash commands now. `pipeline.execute_stage` stays as the library
  hermes/loop call internally.

## Principles

- **Loop engineering** — design loops, stay the engineer. Failures ratchet into
  `skills/` AND are recalled by domain on the next run (closed loop): the loop
  injects past lessons into implement+verify prompts; `/sigma-learn-lesson` lets a
  human ratchet a lesson from any session.
- **Maker ≠ checker** — implementer and verifier are always distinct agents. The
  optional logic-evaluator is a third distinct agent (separation enforced).
- **Plugin-first** — the Claude Code plugin (slash commands + skills, incl.
  `sigma-domains`) is the primary surface. The CLI keeps only what Claude Code
  cannot do in-session (parallel `research`), the autonomous escape hatch
  (`loop`/`hermes`), `board`/`weave`, and setup.
- **Lean context** — load only the domain a task needs (`skills/sigma-domains`
  surfaces it in-session).
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
- `cli/checks.py` probes are **pure** (return `Check`, never print/mutate); a fix
  is a `(description, callable)` the caller applies. `sigma doctor` confirms each
  fix unless `--yes`; `--check` is read-only (exit 1 on any FAIL — CI gate).
- Secrets (`cli/secrets.py`) go ONLY to `~/.sigma/.env` (chmod 600, git-ignored),
  NEVER `sigma.config.yml`. An ambient env var of the same name counts as present.
- RTK install/activate (`cli/rtk.py`) is **confirm-gated** — it touches the global
  `~/.claude/settings.json` via `rtk init -g`, so onboard/doctor always ask first.
  `rtk_status` checks `rtk gain` works to catch the name-collision binary.
- Caveman (`cli/caveman.py`) mirrors RTK exactly: confirm-gated, idempotent, touches
  global plugin/settings state. `setup_caveman` no-ops when already active or when
  the `claude` CLI is absent. Wired into `sigma onboard` (step 7) + `check_caveman`.
- Research is **subscription-backed, no API credit**: gpt runs via `codex exec`
  (ChatGPT login, read-only sandbox), gemini via `gemini -p --output-format json`,
  claude via `claude -p`. `clean_output` normalizes each CLI's raw stdout. The old
  `openai api chat...` adapter was dead (pre-1.0 CLI) and is gone. `check_models`
  probes the real binary (`codex` for gpt), not the model name.
- `sigma research --deep` enables web search/grounding (codex `tools.web_search=true`,
  deep brief demanding live citations), bumps timeout 300s→900s, marks `Mode: deep`
  in the header. `run_research`'s `_call_runner` tolerates 2-arg test fakes (no `deep` kwarg).
- `sigma learn` (`cli/learn.py`) drives the AgentRunner to emit ARCHITECTURE.md + a
  CodeTour `.tours/<slug>.tour`, validated by the pure `cli/codetour.py` (anchors
  must resolve). **No graph engine** — Graphify/tree-sitter need py3.10; we stay 3.9.
  Gotcha: the agent prompt must NOT start with `-` (claude -p reads it positionally
  and a leading dash parses as an option flag); skill blocks use `### skill:` headers.
- `installer/setup.sh` is non-interactive (TTY-safe under `curl|sh`): no `read`.
  All prompts live in `sigma onboard`. Targets Python 3.9 (not 3.10).
- `--gate <script>` (loop/hermes) is a **fail-safe** wakeAgent pre-check: the
  script prints `{"wakeAgent": true|false}`; false skips work (0 tokens). A
  missing/erroring/unparseable gate defaults to WAKE — a broken gate never
  silently blocks the pipeline (the inverse of verdict parsing, which defaults FAIL).
- Contradiction flagging: on ratchet, `skills_index.find_contradictions` matches
  same domain + normalized topic_key. A hit adds a `⚠ CONTRADICTION` marker to the
  new skill + a line in `skills/CONTRADICTIONS.md`. Never auto-resolves or deletes
  — humans decide (`CycleOutcome.contradiction` surfaces it).
- Closed learning loop: `cli/skills_recall.py` (pure) reads lessons back by
  `domain:` match — `recall_lessons` excludes any skill WITHOUT a `domain:` tag
  (so vendor/sigma-present/sigma-domains never leak in), `render_recall_block`
  caps at a limit. `run_loop` builds the block once per domain (cached for the
  whole batch — a lesson ratcheted mid-batch surfaces on the NEXT run, not later
  same-domain tasks in the same batch; snapshot keeps cost bounded + deterministic)
  and `execute_cycle(recall=...)` prepends it to the implement + verify prompts only
  (NOT logic — it grades reasoning, not domain patterns). Empty recall →
  prompts byte-identical (fail-safe). The manual `/sigma-learn-lesson` writes via
  the SAME ratchet format with a `session lesson:` title prefix (added to
  `_NOISE_PREFIXES`) so manual + loop lessons on one topic share a key for both
  contradiction detection and recall.
- `sigma weave` (`cli/weave.py`) produces TWO **derived** outputs in the spec
  workspace — markdown stays the source of truth, so deleting them never affects
  the pipeline. `chain.json` (machine manifest) is written FIRST by the pure
  `weave_manifest.build_manifest` and is **agent-independent** — it exists even if
  the `claude -p` HTML run fails. `chain.html` is agent-emitted and validated by
  the pure `validate_chain_html` guard (structural sanity, never exact bytes).
  `build_manifest` is deterministic: **no timestamp in the pure path** (same
  discipline as `board.Event.ts`). It imports `pipeline.STAGES` (single source);
  `pipeline.py` therefore must NOT import `weave_manifest` (it reads `chain.json`
  directly to avoid the circular import).
- The `verify` STAGE reads the whole artifact chain: `pipeline.chain_context`
  inlines every present file artifact from `chain.json`. **Fail-safe**: missing /
  unreadable `chain.json` → falls back to the single `PRIOR_ARTIFACT` (`spec.md`),
  never hard-fails (a missing derived artifact never blocks the pipeline). Scope is
  stage-verify ONLY — `loop.py`'s per-task `VERIFY_PROMPT` (maker→checker) is
  untouched, so the maker≠checker contract is unchanged.
