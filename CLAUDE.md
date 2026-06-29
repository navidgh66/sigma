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
and are recalled by domain on the next run). An adversarial **`/grill`** gate
pressure-tests the blueprint + spec before code. `sigma learn` grounds its map in a
graphify knowledge graph; `sigma scout` keeps the skill bundle fresh from
skillsmp.com; `sigma prune` cuts unused MCP/plugin context bloat. `sigma eval` runs
eval sets (LM-judge + pass-rate gate); `sigma trajectory` observes what agents
actually did; `--route` (loop/eval) does intelligent model-tier routing. `sigma
session-context` + a SessionStart hook feed `learn` artifacts back into every new
session (closing the learn loop); `loop --simplify` adds a distinct anti-slop
cleanup pass after each verified cycle. 596 pytest tests, ruff clean.

## Commands

```bash
python3 -m pytest tests/ -q          # run all 596 tests (must stay green)
python3 -m ruff check cli/ tests/    # lint (py39 target)
python3 -m ruff check --fix cli/ tests/

python3 -m cli.main --help           # CLI help
sigma init --domains nlp,rl          # scaffold sigma.config.yml for a project
sigma research "topic"               # multi-model research → research.md
sigma research "topic" --web         # quick web-grounded pass (light; --deep wins if both)
sigma research "topic" --deep        # web-grounded deep research (exhaustive web search; slower)
sigma learn                          # learn the codebase → ARCHITECTURE.md + .tours/<slug>.tour (+ graphify graph if installed)
sigma session-context                # print the learn-artifact pointer (wired as a SessionStart hook → every new session reads the map)
sigma learn --no-graph               # skip the graphify knowledge-graph build
sigma learn --persona "new dev" --dry-run  # print the invocation, don't run claude

sigma scout                          # discover skills relevant to your domains on skillsmp.com → install on approval
sigma scout --vendor --recent        # maintainer mode (clone into skills/vendor/), sort by newest
sigma prune                          # surface loaded-but-unused MCP/plugins → reversible disable (saves context tokens)
sigma prune --check                  # read-only; exit 1 if prunable bloat exists (CI)
# Pipeline stages (propose..verify) run IN-SESSION as plugin slash commands
# (/propose .. /verify). They are NOT standalone CLI subcommands — running a
# stage in Claude Code loads the domain context-engine and is steerable; an
# amnesiac `claude -p` subprocess is strictly weaker. See "Two ways to run".

sigma loop --topic <t>               # plan cycles (safe default; autonomous escape hatch)
sigma loop --topic <t> --execute     # run maker→checker cycles
sigma loop --topic <t> --execute --tdd    # test-writer agent pens failing test first (RED→GREEN)
sigma loop --topic <t> --execute --team   # independent tasks run in parallel
sigma loop --topic <t> --execute --logic  # add logic-evaluator axis (combine: --team --tdd --logic)
sigma loop --topic <t> --execute --simplify  # distinct anti-slop cleanup after each PASS (re-verified to preserve behaviour)
sigma loop --topic <t> --execute --route  # intelligent model routing: mechanical→cheap tier, logic→strong tier

# Eval — run an eval set, LM-judge each case, gate at a pass-rate threshold (set the bar at the eval, not the demo)
sigma eval --set <name>              # prompt mode: run each case input through a SUT, grade with a DISTINCT judge
sigma eval --set <name> --artifact spec.md  # artifact mode: grade an existing file vs each case rubric (no SUT run)
sigma eval --set <name> --threshold 0.9     # require a 90% pass rate (default 0.8)
sigma eval --set <name> --check      # CI gate: exit 1 below threshold
sigma eval --set <name> --route      # route the judge to a strong tier

# Trajectory — observe what agents actually did in a workspace (loop/hermes record steps)
sigma trajectory --topic <t>         # summary: step count, failures, per-role/model, total agent time
sigma trajectory --topic <t> --json  # machine-readable summary

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

# Profile + review — team-change review grounded in codebase logic
sigma profile                        # walk codebase → sigma/profile/logic-profile.md (ML + system invariants)
sigma review                         # 3-axis review of local diff vs HEAD (code / ml-logic / system-logic)
sigma review <PR#|url>               # review a PR (gh pr diff) + post a summary comment
sigma review a..b                    # review a git range
sigma review --check                 # CI gate: exit 1 on a CRITICAL/HIGH finding or an inconclusive axis
sigma cost                           # report the token-cost ledger (sigma/costs.jsonl)

# Setup & health
sigma onboard                        # friendly first-run: domains, API keys, RTK, caveman, ccstatusline
sigma doctor                         # diagnose + confirm-gated fixes
sigma doctor --check                 # read-only, exit 1 on any failure (CI)
sigma doctor --yes                   # apply all fixes without prompting
sigma doctor --update                # update BOTH surfaces: git pull the CLI + refresh the plugin (claude plugin update sigma@sigma; restart CC to apply), then check
sigma uninstall                      # reverse the installer: launcher + ~/.sigma + Claude plugin (confirm-gated; --yes to skip; leaves global RTK/caveman/statusline)
```

## Pipeline

`research → propose → blueprint →[grill]→ spec →[grill]→ tasks → implement-task → verify → loop`

Each stage reads the prior stage's artifact as context. Artifacts live under
`sigma/specs/{YYYY-MM-DD}-{slug}/`. `/grill` is an adversarial gate (not a numbered
stage) that pressure-tests the blueprint and the spec before code — skeptical,
maker ≠ griller, BLOCKs on a CRITICAL/HIGH logic flaw (human may override). In the
**autonomous** `hermes --auto` chain the two gates ARE pipeline stages —
`grill-blueprint` (after blueprint) + `grill-spec` (after spec), both reusing the
single `commands/grill.md` template via a `--target`; a BLOCK verdict halts the
chain at a `grill-blocked` human gate (mirrors the verify-failed gate).
`/grill-loop` wraps it in a bounded grill→triage→edit→re-grill cycle: a DISTINCT
editor agent auto-applies only **mechanical** fixes (add BDD scenario, pin
version, define term, add implied edge case); **CRITICAL + any intent-changing**
finding is SURFACED to a human, never auto-edited. Stops on READY, a round cap
(default 3), or no-progress (CRIT+HIGH didn't drop). SURFACED ≠ READY — honest
about what's unresolved. Editor ≠ griller, same law as `execute_cycle`.

## Layout

```
cli/__init__.py     __version__
cli/main.py         argparse CLI: init / research / loop / hermes / board / weave / doctor / onboard / learn / scout / prune / profile / review / eval / trajectory / cost / launch (pipeline stages are plugin-only)
cli/config.py       sigma.config.yml load/write/validate + local override merge
cli/paths.py        DOMAINS (9), project root, spec workspace, slugify
cli/models.py       research adapters (claude -p / gemini -p --json / gpt via codex exec); clean_output; deep_args
cli/research.py     parallel fan-out + cited aggregation → research.md; --web quick / --deep exhaustive web-grounded brief
cli/learn.py        sigma learn — agent-driven codebase walkthrough → ARCHITECTURE.md + .tours/<slug>.tour; always-on graphify build (--no-graph to skip) injects GRAPH_REPORT.md into the prompt
cli/graphify.py     pure+injectable: detect/install (uv→pipx→pip)/setup graphify (confirm-gated), build extract argv, read GRAPH_REPORT.md as a capped prompt block — shells out, never imports (sigma stays 3.9)
cli/scout.py        pure: domain→query map, score_relevance, rank, dedup_against_bundle, parse skillsmp /search payload (sigma scout)
cli/scout_run.py    thin: stdlib urllib fetch (fail-safe), aggregate per-domain, surface ranked candidates, git-clone on per-skill confirm
cli/prune.py        pure: parse_plugins/parse_mcp_servers, belongs (tool→item match), usage_counts, rank_candidates (unused+heavy first), context-weight estimate
cli/prune_run.py    thin: read settings/.claude.json/.mcp.json + scan transcripts for usage, build report, reversible disable (enabledPlugins=false, immutable merge)
cli/codetour.py     pure CodeTour .tour validator (file exists / line in range / pattern present)
cli/runner.py       AgentRunner — the single execution chokepoint (injectable); optional `model` (→ --model alias, intelligent routing) + `trajectory_sink` (observability), both fail-safe no-ops by default
cli/trajectory.py   pure: append-only trajectory.jsonl (one step/agent run: role/model/ok/duration) + summarize projection + make_sink (best-effort, never breaks a run)
cli/session_context.py  pure: build_pointer(root) → names ARCHITECTURE.md + .tours/*.tour for a SessionStart hook (lazy /learn hint when absent); never raises (read side of learn)
cli/session_hook.py     thin: confirm-gated idempotent install of the SessionStart hook into project .claude/settings.json (immutable merge, like statusline.py)
cli/claude_local.py     pure upsert_block (marker-delimited) + thin write_block into gitignored CLAUDE.local.md — static fallback for the learn pointer
cli/eval.py         pure: parse eval set (markdown cases) + build LM-judge prompt + skeptical parse_grade + aggregate/gate(threshold) + ensure_distinct (SUT≠judge)
cli/eval_run.py     thin: resolve eval set, prompt mode (run SUT → grade w/ distinct judge) or artifact mode, parallel grading fan-out, cost record, write report, --check gate
cli/pipeline.py     execute_stage library (used by hermes/loop): run stage, chain prior artifact, persist; verify reads full chain via chain.json. STAGES includes the two grill GATE stages (grill-blueprint/grill-spec, shared grill template via `template` key + GRILL_TARGET)
cli/weave.py        sigma weave — agent-driven: stage artifacts → chain.html (manifest written first, agent-independent)
cli/weave_manifest.py  pure: build_manifest → chain.json contract + validate_chain_html guard
cli/domains_index.py  pure: resolve each domain → implementer/verifier/logic-evaluator files; powers skills/sigma-domains
cli/loop.py         parse tasks, execute_cycle (maker→checker + logic + optional TDD test-writer + optional post-pass --simplify cleanup w/ re-verify guard), run_loop (sequential or --team parallel)
cli/hermes.py       conductor: route → inject skill → execute_stage → emit event
cli/intent.py       hybrid routing: state-scan default + intent-override classify
cli/skill_map.py    stage → bundled skill mapping; inject_skill into prompts
cli/events.py       append/read events.jsonl — append-only board state spine
cli/board.py        kanban projection (pure build_columns) + rich static/live render
cli/keepawake.py    --keep-awake: caffeinate wrapper, prevents Mac sleep on long runs
cli/checks.py       pure diagnostic probes (python/deps/models/secrets/skills/plugin/config/workspaces/rtk/caveman/statusline/graphify)
cli/doctor.py       sigma doctor — run checks, confirm-gated fixes, --check/--yes/--update (dual-surface: CLI git pull + plugin update)
cli/onboard.py      sigma onboard — first-run setup: domains, API keys, sign-in guide, RTK, caveman, ccstatusline, graphify, SessionStart hook, + offer to build learn artifacts (step 11, confirm-gated, no-op if they exist; learn_fn injectable so tests never spawn an agent)
cli/uninstall.py    pure build_plan (launcher/~/.sigma/plugin surfaces) + run_uninstall (confirm-gated, separate .env-secrets confirm, best-effort, injectable I/O); leaves global RTK/caveman/statusline
cli/secrets.py      ~/.sigma/.env key store (chmod 600) — never the committed config
cli/rtk.py          detect/install/activate RTK token-saver (confirm-gated, idempotent)
cli/caveman.py      detect/install caveman terse-output mode (confirm-gated, RTK-shaped)
cli/statusline.py   detect/configure ccstatusline status line (confirm-gated; writes settings.json statusLine, preserves other keys)
cli/render.py       σ logo + update banner + rich/plain check output + confirm prompt
cli/gate.py         wakeAgent gate — cheap pluggable pre-check, skip work (0 tokens)
cli/skills_index.py topic-key + contradiction detection across ratcheted skills
cli/skills_recall.py  pure: recall_lessons(skills_dir, domain) + render_recall_block — read side that closes the learning loop
cli/review.py       pure: change-set parse, domain infer, 3-axis prompt build, finding parse/aggregate/dedup, gate (fail on CRIT/HIGH or inconclusive axis), distinct-axis guard
cli/review_run.py   thin: resolve change set (git diff / gh pr diff), parallel 3-axis fan-out, write report, PR comment, ratchet CRIT/HIGH → skills/, record cost
cli/profile_manifest.py  pure: logic-profile skeleton + validate (both sections) + staleness(profile, files) banner
cli/profile_run.py  thin: AgentRunner walker → sigma/profile/logic-profile.md (ML-logic + system-logic invariants)
cli/cost.py         pure: estimate(op,units) + model-tier routing + calibrate from ledger + record contract + report; fail-safe to static factors
commands/           slash-command templates (one per stage + /grill + /grill-loop + /learn + /scout + /prune + /weave + /profile + /review + /eval + /sigma-learn-lesson), YAML frontmatter
context-engines/<d>/  9 domains, implementers/ + verifiers/ (each has logic-evaluator.md) — surfaced in-session via skills/sigma-domains
subagents/researchers/  claude / gemini / gpt research subagents (CLI fan-out + /research in-session)
skills/             ratcheted lessons (SKILL.md): written on loop failures + by /sigma-learn-lesson; recalled by domain next run
skills/vendor/      bundled skills (superpowers subset + caveman + code-tour + codebase-onboarding) — self-contained
skills/sigma-present/  skill: export artifacts → single-file HTML deck/report/kanban
skills/sigma-domains/  skill: auto-surface the right domain context-engine (indexes context-engines/, no duplication)
skills/sigma-lessons/  skill: recall past ratcheted lessons by domain in-session (read side of the loop)
skills/sigma-grilling/  skill: the grilling rubric — adversarially interrogate a blueprint/spec before code (powers /grill); maker ≠ griller, BLOCK on doubt; per-axis decomposed scoring (AXIS lines + derived overall VERDICT), 11 axes incl. singular-requirement / EARS error-path / traceability / constitution / behaviour-orientation (evidence-backed: decomposed grading ≈2× expert correlation vs holistic)
skills/sigma-grill-loop/  skill: bounded auto-grill loop (powers /grill-loop) — grill→triage→edit→re-grill; editor ≠ griller, mechanical-only auto-edit, CRITICAL/intent surfaced, round cap + no-progress stop
skills/sigma-cost/  skill: estimate/measure/route token cost for heavy ops (review/profile/loop/research); composes with RTK/caveman, never duplicates
skills/sigma-scout/  skill: curation rubric for sigma scout — relevance > popularity, license/overlap vetting, surface never auto-install
skills/sigma-prune/  skill: pruning rubric — never prune on absent evidence, disable ≠ delete; composes with scout (grows) + cost (sizes)
installer/setup.sh  one-line install: CLI + deps + plugin auto-register + RTK + graphify (TTY-safe)
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
- `--tdd` adds a distinct TEST-WRITER agent that pens a FAILING test BEFORE the
  implementer (RED), whose prompt is then prefixed with that test ("make it pass,
  don't weaken it" = GREEN). Enforced distinct from maker/checker/logic
  (`ValueError` on reuse — uses `is`, not `==`, because AgentRunner is a dataclass
  and two fresh instances compare equal). A failed test-writing step aborts the
  cycle (nothing to build against) and ratchets the failure; the maker never runs.
  `CycleOutcome.test_written` is set only in TDD mode. On a VERIFY failure in TDD
  mode the same test-writer pens a REGRESSION test pinning the bug the checker found
  (`workspace/regressions/`, `CycleOutcome.regression_test`) — best-effort, a failed
  write is noted, never fatal; the lesson still ratchets. Only fires on verify-fail
  (a real bug), not impl/test-write crashes; no test-writer → no regression artifact.
- `--team` runs the capped task batch CONCURRENTLY (ThreadPoolExecutor). The recall
  snapshot is pre-built for every batch domain BEFORE fan-out, so parallel threads
  only READ it — no races, deterministic. Result order matches batch order.
  Sequential (default) is unchanged. Combine `--team --tdd --logic` freely.
- `sigma research --web` is a quick web-grounded pass (lighter brief, same web
  toggle as `--deep`); `--deep` is exhaustive (900s). `--deep` wins if both given.
  Both flip the SAME adapter web-search path (`run_research`'s `web_search = deep
  or web`); only the brief + timeout differ.
- `sigma hermes` runs ONE stage by default; `--auto` chains until a human gate
  (spec-approval, **grill-blocked**, verify-failed), a stage failure, or the hop
  budget (`max_hops`). The grill gates (`grill-blueprint`/`grill-spec`) run the
  shared `commands/grill.md` with a `--target`; `hermes._grill_ready` parses the
  verdict skeptically (no `VERDICT: READY` → BLOCK, same default-deny as
  `_verdict_pass`) and a BLOCK stops the chain at `grill-blocked` for human review.
  `_grill_ready` matches ONLY the final `VERDICT:` line — the rubric's per-axis
  `AXIS | <name> | PASS|FAIL` lines (decomposed scoring) precede it and are
  parser-inert by design (regression-locked by `test_grill_ready_ignores_per_axis_lines`).
  Overall verdict is DERIVED: any axis with a CRITICAL/HIGH finding → BLOCK.
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
- `--update` refreshes **both** install surfaces — they are separate dirs on disk:
  the CLI (`git pull --ff-only` on `sigma_home`) AND the Claude Code plugin
  (`claude plugin marketplace update sigma` + `claude plugin update sigma@sigma`).
  The plugin step is guarded by `which("claude")` (skipped silently when absent,
  like caveman/rtk) and applies on CC restart. `_default_updater`'s `spawn`/`which`
  are injectable (host-free tests). A git pull alone never reaches the plugin —
  that's why the plugin slash-commands lagged before this. `--update` prints the
  σ banner (`render.print_update_banner`) first.
- Secrets (`cli/secrets.py`) go ONLY to `~/.sigma/.env` (chmod 600, git-ignored),
  NEVER `sigma.config.yml`. An ambient env var of the same name counts as present.
- RTK install/activate (`cli/rtk.py`) is **confirm-gated** — it touches the global
  `~/.claude/settings.json` via `rtk init -g`, so onboard/doctor always ask first.
  `rtk_status` checks `rtk gain` works to catch the name-collision binary.
- Caveman (`cli/caveman.py`) mirrors RTK exactly: confirm-gated, idempotent, touches
  global plugin/settings state. `setup_caveman` no-ops when already active or when
  the `claude` CLI is absent. Wired into `sigma onboard` (step 7) + `check_caveman`.
- ccstatusline (`cli/statusline.py`) mirrors caveman's shape but is NOT a plugin:
  it writes a `statusLine` command block into the GLOBAL `~/.claude/settings.json`,
  preserving every other key (immutable merge — new dict, never mutate the loaded
  one). Confirm-gated + idempotent: `setup_statusline` no-ops when a statusLine is
  already configured or when no node runtime (`npx`/`bunx`) is on PATH. Uses
  `npx -y ccstatusline@latest` so no global install is required. Wired into
  `sigma onboard` (step 8) + `check_statusline`. `which`/`writer` injectable
  (host-free tests never touch the real settings.json).
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
- `sigma review` / `/review` review TEAM changes (local diff or PR), distinct from
  the `verify` STAGE (which grades sigma's own pipeline artifacts). Three distinct
  axes — code / ml-logic / system-logic — enforced distinct via
  `review.ensure_distinct_axes` (the maker≠checker analog; `ValueError` on reuse).
  Axes parse `FINDING | SEV | file:line | msg` lines; the gate FAILs on any
  CRITICAL/HIGH finding **or** any inconclusive axis (a dead axis is never a silent
  pass — skeptical, like `_verdict_pass`). CRITICAL/HIGH findings ratchet into
  `skills/` (recalled next review) via the SAME `loop.ratchet_to_skills`.
- `review.infer_domains` defaults to **`classic-ml`** (NOT ai-agent-engineering)
  when no path hint matches — the ml-logic axis must grade generic ML invariants
  (leakage/splits/metrics), and the agent logic-evaluator would be structurally
  silent on those. Multi-domain changes union each domain's recall + logic-evaluator.
- The logic profile (`sigma/profile/logic-profile.md`, built by `/profile`) grounds
  review. **Fail-safe**: missing profile → review proceeds on diff + lessons with a
  banner; stale profile (older than touched files, mtime-based) → warns, proceeds
  (never blocks — Q3 freshness=staleness-flagged). `profile_manifest` is pure (no
  clock/subprocess); both invariant sections are mandatory (`validate_profile`).
- Cost loop (`cli/cost.py`, `skills/sigma-cost`): `estimate(op, units)` before a
  heavy op (advisory + model-tier routing), `record` after into `sigma/costs.jsonl`
  (append-only like `events.jsonl`; caller passes `ts`, never generated in pure
  code), `calibrate` sharpens factors from the ledger. **Fail-safe**: missing/garbage
  ledger → static factors, never blocks. Distinct LAYER from RTK (proxy token cut)
  and caveman (output terseness) — it may recommend them, never duplicates them.
- Live `sigma review`/`profile` write under `sigma/reviews/` + `sigma/profile/` +
  `sigma/costs.jsonl` in the TARGET project (git-ignored here) — they are derived,
  deleting them never affects the pipeline. A real review run also ratchets findings
  into `skills/`; those are real lessons, not throwaway (unlike a smoke test's).
- `sigma learn` SHELLS OUT to graphify, it does NOT import it. graphify needs
  py3.10+; sigma stays 3.9 by installing graphify in its OWN isolated env (`uv tool
  install graphifyy` / pipx) and subprocessing the `graphify` binary — the same
  pattern as `claude`/`gemini`/`codex`/`rtk`. The OLD "no graph engine" rule meant
  "don't import one", NOT "don't use one". `cli/graphify.py` is the seam: build is
  always-on (`--no-graph` to skip) + best-effort (a failed/absent build degrades to
  a plain agent read), and `report_block` injects GRAPH_REPORT.md only if present —
  empty → the learn prompt is byte-identical to the pre-graphify prompt (regression-
  locked by `test_no_graph_prompt_byte_identical_to_baseline`). `check_graphify` is
  WARN-never-FAIL (optional, like rtk/caveman); onboard step 9 + setup.sh step 6
  install it confirm-gated.
- `sigma scout` (`cli/scout.py` pure / `cli/scout_run.py` thin) queries skillsmp.com
  via **stdlib urllib** (NO `requests` dep — keep the runtime pyyaml+rich only).
  Relevance score is **whole-token** domain-keyword-overlap-dominant (NOT substring —
  `rag` no longer credits "sto**rag**e"/"f**rag**ment") with a CAPPED star bump, so a
  popular-but-irrelevant skill never outranks a relevant one (asserted in tests). `rank`
  enforces a **relevance FLOOR** (`_RELEVANCE_FLOOR=1.5`, just above the ≤1.0 star bump →
  a hit needs ≥1 real token overlap) so pure noise is DROPPED, not just out-ranked, plus
  a **per-author cap** (`max_per_author`) so one publisher can't flood the table.
  Dedups against `skills/` + `skills/vendor/` by normalized repo AND dir name. NEVER
  auto-installs — per-skill human confirm (surface, never auto-resolve, like
  contradiction flagging). `--vendor` clones into the sigma bundle, default into the
  project's `.claude/skills/`. `SKILLSMP_API_KEY` is OPTIONAL (env or ~/.sigma/.env,
  NEVER prompted in onboard, never committed). Fail-safe: API down/rate-limited/bad
  JSON → empty result + banner, never a crash; a partial sweep still ranks.
- `sigma prune` (`cli/prune.py` pure / `cli/prune_run.py` thin) cuts loaded-but-
  unused MCP servers + plugins (each injects tool schemas into EVERY context). Two
  hard laws: (1) **never prune on absent evidence** — no transcripts scanned →
  surface NOTHING (an item with unknown usage is treated as USED, the conservative
  default, like gate-defaults-WAKE); (2) **disable ≠ uninstall** — flips
  `enabledPlugins[name]=false` in settings.json via an IMMUTABLE merge (new dict,
  every other key preserved, exactly like `cli/statusline.py`), reversible by
  flipping back. User-level MCP servers (`~/.claude.json`) are SURFACED for a manual
  edit — prune never auto-edits that file. `--check` is a read-only CI gate (exit 1
  on prunable bloat). Distinct hygiene LAYER: scout grows the bundle, prune trims it,
  sigma-cost sizes it. **Weight scales with REAL schema width**: a server's context
  weight = its distinct `mcp__<server>__*` tool count (scanned across history) ×
  `_PER_TOOL_WEIGHT`, NOT a flat per-kind constant — a 100-tool server dwarfs a 2-tool
  one; unknown count → per-kind fallback (`prune_run.tool_counts_by_server` +
  `_with_tool_count`). Two scan windows: FULL `--files` scan = schema width (recency-
  independent), RECENT `--recent-files N` = the usage window (prune servers idle
  *lately* even if hot long ago; defaults to the full scan = prior behavior).
  `--idle-threshold N` surfaces items used ≤N times as `low_confidence` candidates
  (judgment call, never auto-disabled; default 0 = unused-only). `belongs` normalizes
  `-`/`_` separators so a HYPHENATED plugin name (`code-review`) still matches its
  `mcp__plugin_code-review_...` tools (was a false-negative → wrong prune candidate).
- `sigma eval` (`cli/eval.py` pure / `cli/eval_run.py` thin) runs an EVAL SET (the
  paper's "set the bar at the eval, not the demo"). Eval sets are markdown
  (`sigma/evals/<name>.md`, `## case:` blocks with input + expected/rubric). Two
  modes: PROMPT (run each input through a system-under-test agent, grade the output)
  and ARTIFACT (`--artifact <file>` grades an existing file vs each rubric, no SUT
  run). The LM judge is a DISTINCT agent from the SUT — `eval.ensure_distinct` raises
  `ValueError` on reuse (`is`, not `==`, like maker≠checker), enforced per case in
  prompt mode. `parse_grade` is SKEPTICAL (missing `VERDICT: PASS` → FAIL, same
  default-deny as the loop/review). `gate(threshold=0.8)` FAILs below the bar AND on
  an empty set (a dead eval is never a silent pass). Grading fans out in parallel
  (`ThreadPoolExecutor`, CLI-only like review). `--check` exits 1 below threshold.
  Report → `sigma/evals/<name>/report.md` (git-ignored, derived); a sample set ships
  at `sigma/evals/sample.md`. Cost op `"eval"` records into the ledger; routing puts
  the judge on a strong tier.
- Model routing + trajectory both extend `AgentRunner` via OPTIONAL fields that
  default to prior behavior (a bare `AgentRunner()` is byte-identical). `model` →
  injects `--model <alias>` into the argv (alias passed straight through — no
  model-ID map to drift); `--route` on `loop`/`eval` wires `cost.routing_for(op)`
  onto the factories (mechanical roles→cheap/mid, reasoning role→strong). OFF by
  default = no behavior change (so `--model` validity per claude version can't break
  an unrouted run). `trajectory_sink` is a best-effort `Callable[[dict], None]`
  called once per run — a failing sink is SWALLOWED (observability must never break a
  run, the inverse of a hard gate). `AgentRunner.run` gained a `role=` label
  (default `"agent"`); loop/hermes pass it (implementer/verifier/logic/test-writer/
  eval-sut/eval-judge) so the trajectory can attribute steps. Test fakes that
  subclass AgentRunner must accept `role=` in their `run` signature.
- `cli/trajectory.py` (pure, like `events.py`) appends one step per agent run to
  `trajectory.jsonl` in the workspace; caller passes `ts` (no clock in the pure
  path). `summarize` is a deterministic projection. `sigma trajectory --topic <t>`
  renders it. Missing file → empty (lenient read-model). Git-ignored (derived).
- `sigma session-context` (`cli/session_context.py` pure) closes the LEARN loop —
  the read side of `sigma learn`. `build_pointer(root)` names the durable learn
  artifacts (ARCHITECTURE.md + `.tours/*.tour`) so a Claude Code SessionStart hook
  surfaces them at the start of EVERY session; neither present → a lazy "run /learn"
  hint, so the hook always emits something. It is PURE (only stats the tree, no
  clock/mutation) and NEVER raises — `cmd_session_context` wraps it and ALWAYS exits
  0 (a session-start hook must never break a session; inverse of verify's
  default-FAIL — here errors degrade to the harmless hint). Two surfaces:
  `cli/session_hook.py` (confirm-gated, idempotent install of the hook into the
  PROJECT `.claude/settings.json` via an IMMUTABLE merge — exactly like
  `cli/statusline.py`; appends to any existing SessionStart hooks, never replaces)
  and `cli/claude_local.py` (`upsert_block` — pure insert/replace between
  `<!-- sigma:learn:start/end -->` markers in the gitignored `CLAUDE.local.md`, the
  static fallback for hook-less envs). `sigma learn` calls `_refresh_local_pointer`
  after writing artifacts (best-effort, never fatal — same fail-safe as the graphify
  build). Onboard step 10 offers the hook (confirm-gated). NOTE: the installed CLI
  runs from `~/.sigma` (separate checkout), so the `sigma session-context` hook
  command resolves only after the install updates (`sigma doctor --update`) — the
  two-surface split.
- `loop --simplify` adds a DISTINCT anti-slop SIMPLIFIER agent (the paper's "70%
  problem" cleanup; Anthropic ships the same as bundled `/simplify`). It runs ONLY
  AFTER a cycle PASSES — cleanup, NOT a gate (a failed cycle never reaches it;
  `CycleOutcome.simplified` stays None). Enforced distinct from
  implementer/verifier/logic/test-writer via the `is`-identity `ValueError` (NOT
  `==` — AgentRunner is a dataclass, two fresh instances compare equal; same law as
  maker≠checker). Behaviour-preservation guard: after the simplifier edits, the SAME
  verifier RE-VERIFIES; `simplified=True` only when re-verify PASSES — a regression
  reverts the simplify, NEVER the feature, and the cycle stays GREEN regardless
  (`_run_simplify` is best-effort: a simplifier crash or re-verify FAIL is logged,
  the passing cycle stands). Four-axis rubric (reuse / simplify / efficiency /
  right-altitude) in `skills/vendor/code-simplifier/SKILL.md` (a sigma-authored
  vendored skill — `skill_map` maps stage `simplify`→`code-simplifier`, added to
  `_TOP_LEVEL` since it lives at `vendor/<slug>/`, not under `superpowers/`). The
  simplifier is NOT given recall (it grades form, not domain patterns — same reason
  logic is excluded). `--simplify` routes to the `implement` tier under `--route`.
- `sigma uninstall` (`cli/uninstall.py`) reverses the installer's CORE surfaces
  only: the launcher (`~/.local/bin/sigma`), the clone (`~/.sigma`, which holds the
  `.env` API keys), and the Claude plugin + marketplace. It deliberately LEAVES the
  shared global state (RTK / caveman / ccstatusline / SessionStart hook in the
  user's `~/.claude/settings.json`) — those may be wanted independently; remove by
  hand. `build_plan` is pure (stats the FS, `which` injectable); `run_uninstall` is
  confirm-gated per surface with a SEPARATE secret-warning confirm before deleting
  `~/.sigma/.env` (API keys never dropped silently), best-effort (an OSError is
  recorded in `result.errors`, never raised — one stuck surface never blocks the
  rest). `spawn`/`rmtree`/`unlink` injectable (tests delete nothing). `--yes` skips
  prompts. Plugin ops skipped when `claude` CLI absent.
