# CLAUDE.md — sigma

Guide for AI assistants working in the sigma repo.

**Reference:** read `ARCHITECTURE.md` for the full architecture map. If it does
not exist, run `sigma learn` (or `/sigma:learn`) to generate it first.

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
actually did; model-tier routing is ON BY DEFAULT across loop/hermes/research
(`--no-route` opts out; eval keeps opt-in `--route`). `sigma
session-context` + a SessionStart hook feed `learn` artifacts back into every new
session (closing the learn loop); `loop --simplify` adds a distinct anti-slop
cleanup pass after each verified cycle. `sigma usage` wraps ccusage for real
Claude Code token/cache/cost visibility, distinct from `sigma cost`'s own
op-ledger. Research now fans out to a second HTTP search-tool provider tier
(Firecrawl) alongside the subscription model CLIs, with a real cross-referencing
synthesis pass; on `--deep` the Firecrawl tier also scrapes the top-3 result
pages for full content, not just search snippets. `/e2e` makes spec.md's BDD
`Scenario/Given/When/Then` blocks executable — an agent drives them live
against the running app (PASS/FAIL/ERROR, ratcheting only real FAILs); `sigma
loop --e2e` gates each task's cycle on its mapped scenario the same way
`--logic` gates on the logic-evaluator axis, and `/implement-task` runs the
same per-task check. `sigma onboard` offers to sign in to Codex
(`codex login`, ChatGPT subscription, no API key) for research's gpt lane and
`loop --codex-verify`/`--codex-tdd`; `sigma doctor` surfaces + can fix a missing
sign-in the same way it does RTK/caveman. `sigma claude-md-check` / `/claude-md-check`
grade CLAUDE.md + CLAUDE.local.md against best-practice research (length,
pasted-code, stale @imports/test-counts, structure); `sigma claude-md-create` /
`/claude-md-create` scaffold a best-practice-shaped starter; `setup-repo` wires
both in automatically. Agent runs parse `claude --output-format json` result
envelopes → REAL token/cost telemetry on trajectories + a self-calibrating cost
ledger; `sigma lessons` correlates recalled lessons with real cycle outcomes
(reversible archive of dead lessons); `sigma docs-check` gates version parity +
stale test-count claims across doc surfaces; `sigma eval --from-spec` renders a
spec's BDD scenarios into an eval set; the loop's verify/logic checkers receive
each task's mapped scenario as acceptance criteria. `sigma trajectory --economy`
joins real per-axis token spend with per-axis value events (from the cycle
step's effect flags) → ranks each loop axis by tokens-per-value-event and
surfaces idle-but-expensive axes as prune candidates (surface-only, never
auto-disabled). 935 pytest tests, ruff clean.

## Commands

```bash
python3 -m pytest tests/ -q          # run all 935 tests (must stay green)
python3 -m ruff check cli/ tests/    # lint (py39 target)
python3 -m ruff check --fix cli/ tests/

python3 -m cli.main --help           # CLI help
sigma init --domains nlp,rl          # scaffold sigma.config.yml for a project
sigma research "topic"               # multi-model research → research.md
sigma research "topic" --web         # quick web-grounded pass (light; --deep wins if both)
sigma research "topic" --deep        # web-grounded deep research (exhaustive web search; slower)
sigma research "topic" --no-route    # disable synthesis routing (default: synthesis→strong tier)
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
sigma loop --topic <t> --execute     # run maker→checker cycles — logic/simplify/advisor/e2e ON by default
sigma loop --topic <t> --execute --no-logic --no-simplify --no-advisor --no-e2e  # bare maker→checker only
sigma loop --topic <t> --execute --tdd    # test-writer agent pens failing test first (RED→GREEN) — opt-in
sigma loop --topic <t> --execute --codex-verify   # verifier via codex CLI — cross-provider maker≠checker, opt-in
sigma loop --topic <t> --execute --tdd --codex-tdd  # test-writer via codex CLI, opt-in (requires --tdd)
sigma loop --topic <t> --execute --team   # independent tasks run in parallel — opt-in
sigma loop --topic <t> --execute --all    # every axis on, incl. --tdd --team
sigma loop --topic <t> --execute --no-route  # disable model routing (routing is ON by default: mechanical→mid, logic/advisor/e2e→strong; --route is a deprecated no-op)

# Eval — run an eval set, LM-judge each case, gate at a pass-rate threshold (set the bar at the eval, not the demo)
sigma eval --set <name>              # prompt mode: run each case input through a SUT, grade with a DISTINCT judge
sigma eval --set <name> --artifact spec.md  # artifact mode: grade an existing file vs each case rubric (no SUT run)
sigma eval --set <name> --threshold 0.9     # require a 90% pass rate (default 0.8)
sigma eval --set <name> --check      # CI gate: exit 1 below threshold
sigma eval --set <name> --route      # route the judge to a strong tier
sigma eval --from-spec <topic>       # generate sigma/evals/<slug>.md from the topic's spec.md BDD scenarios (--force to regenerate)

sigma lessons                        # lesson-efficacy report over ALL workspaces: working / not-working / no-evidence
sigma lessons --topic <t>            # restrict evidence to one topic's workspace
sigma lessons --archive              # offer to move never-recalled lessons to skills/archive/ (confirm-gated, reversible)

sigma docs-check                     # cross-surface consistency: version parity + stale test-count claims; --check for CI

# Trajectory — observe what agents actually did in a workspace (loop/hermes record steps)
sigma trajectory --topic <t>         # summary: step count, failures, per-role/model, total agent time
sigma trajectory --topic <t> --json  # machine-readable summary

# Hermes — autonomous CLI conductor (escape hatch for hands-off runs)
sigma hermes "continue" --topic <t>         # route → run ONE stage, then stop
sigma hermes "build it" --topic <t> --auto  # chain stages until a human gate
sigma hermes "..." --topic <t> --terse      # compress output (caveman skill)
sigma hermes "..." --topic <t> --no-route   # disable per-stage routing (default: planning/grill→strong, execution→mid)

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
sigma claude-md-check                # check CLAUDE.md + CLAUDE.local.md vs best-practice research; --check for CI
sigma claude-md-create --target repo # scaffold a best-practice-shaped CLAUDE.md (capped ~200 lines); --target local for CLAUDE.local.md
sigma cost                           # report sigma's OWN heavy-op token-cost ledger (sigma/costs.jsonl)
sigma usage                          # real Claude Code token/cache/cost via ccusage (wraps `npx ccusage@latest`)
sigma usage claude session --json    # passthrough args forward to ccusage unmodified

# Setup & health
sigma onboard                        # friendly first-run: domains, API keys, RTK, caveman, ccstatusline
sigma doctor                         # diagnose + confirm-gated fixes
sigma doctor --check                 # read-only, exit 1 on any failure (CI)
sigma doctor --yes                   # apply all fixes without prompting
sigma doctor --update                # update BOTH surfaces: git pull the CLI + refresh the plugin (claude plugin update sigma@sigma; restart CC to apply), then check
sigma uninstall                      # reverse the installer: launcher + ~/.sigma + Claude plugin (confirm-gated; --yes to skip; leaves global RTK/caveman/statusline)
sigma setup-repo                     # one-shot per-repo bootstrap: config + SessionStart hook + CLAUDE.local + codebase map (--no-learn skips the agent map; --domains for config)
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

`/craft` (plugin-only slash command, no Python backing) is the in-session
BACK-HALF conductor: you bring a design/plan/big-spec (pasted, a file path, or an
existing `architecture.md`) and it drives `spec → /grill → tasks → /loop` — the
implementation half only, skipping `research → propose → blueprint` (that's what
`hermes --auto` does from a blank start). Same gates as hermes (grill BLOCK,
spec-approval, verify-fail); the design is the human's input — `/craft` never
fabricates it. It is the in-session sibling of `hermes --auto`, entered from a
design instead of an idea.

## Layout

```
cli/__init__.py     __version__
cli/main.py         argparse CLI: init / research / loop / hermes / board / weave / doctor / onboard / learn / scout / prune / profile / review / eval / trajectory / cost / usage / launch (pipeline stages are plugin-only)
cli/config.py       sigma.config.yml load/write/validate + local override merge (incl. optional `research.tools`, default empty)
cli/paths.py        DOMAINS (9), project root, spec workspace, slugify
cli/models.py       tier-1 model-CLI adapters (claude -p / gemini -p --json / gpt via codex exec); clean_output; deep_args
cli/research_brief.py  canonical brief templates (quick/web/deep) + shared citation/confidence rules — single source of truth consumed by cli/research.py + cli/research_docs.py
cli/search_providers.py  tier-2 HTTP search-tool adapters (Firecrawl first); stdlib urllib, ModelResult-shaped output so aggregate()/synthesize() treat both tiers uniformly; opt-in via FIRECRAWL_API_KEY; on deep=True scrapes top-3 deduped result URLs (/v1/scrape) for full-page content, capped + truncated (_SCRAPE_TEXT_CAP), folded into the same findings text — snippet-only when deep=False, byte-identical to pre-deep-crawl output
cli/research.py     two-tier parallel fan-out (model CLIs + search tools) + manual-findings reader + REAL cross-referencing synthesis pass (claude_synthesis_runner default) → cited research.md; --web quick / --deep exhaustive web-grounded brief
cli/research_docs.py  pure render functions: generate the shared-rules marker block for commands/research.md + persona docs from research_brief.py; regenerate via scripts/regen_research_docs.py
cli/usage.py        thin ccusage wrapper (node-runtime detection + argv builder) — real Claude Code session token/cache/cost via `npx ccusage@latest`, distinct from cli/cost.py's own op-ledger
cli/learn.py        sigma learn — agent-driven codebase walkthrough → ARCHITECTURE.md + .tours/<slug>.tour; always-on graphify build (--no-graph to skip) injects GRAPH_REPORT.md into the prompt
cli/graphify.py     pure+injectable: detect/install (uv→pipx→pip)/setup graphify (confirm-gated), build extract argv, read GRAPH_REPORT.md as a capped prompt block — shells out, never imports (sigma stays 3.9)
cli/scout.py        pure: domain→query map, score_relevance, rank, dedup_against_bundle, parse skillsmp /search payload (sigma scout)
cli/scout_run.py    thin: stdlib urllib fetch (fail-safe), aggregate per-domain, surface ranked candidates, git-clone on per-skill confirm
cli/prune.py        pure: parse_plugins/parse_mcp_servers, belongs (tool→item match), usage_counts, rank_candidates (unused+heavy first), context-weight estimate
cli/prune_run.py    thin: read settings/.claude.json/.mcp.json + scan transcripts for usage, build report, reversible disable (enabledPlugins=false, immutable merge)
cli/codetour.py     pure CodeTour .tour validator (file exists / line in range / pattern present)
cli/runner.py       AgentRunner — the single execution chokepoint (injectable); optional `model` (→ --model alias, intelligent routing) + `trajectory_sink` (observability), both fail-safe no-ops by default
cli/trajectory.py   pure: append-only trajectory.jsonl (one step/agent run: role/model/ok/duration + measured tokens/cost + cycle domain/lesson provenance + per-axis effect flags logic_ok/advised/e2e_ok/simplified/test_written) + summarize/efficiency projections + make_sink/counting_sink (best-effort, never breaks a run)
cli/axis_economy.py pure: per-axis token-economy projection — joins tokens-per-role (real telemetry only) with per-axis value events (from cycle-step effect flags) → build_economy/AxisEconomy.render; flags idle-but-expensive axes as prune candidates (surface-only); powers `sigma trajectory --economy`
cli/telemetry.py    pure: parse_result_envelope for `claude -p --output-format json` stdout → UsageEnvelope (text + REAL input/output/cache tokens + cost_usd); lenient — malformed → None, caller falls back to plain text
cli/lessons.py      pure: lesson-efficacy projection (cycle recall provenance × outcomes → working/not-working/no-evidence) + reversible archive_lesson (skills/archive/, never a delete); powers `sigma lessons`
cli/docs_check.py   pure: cross-surface consistency checks (version parity cli/__init__.py ↔ plugin.json; stale test-count claims) → review.Finding
cli/docs_check_run.py  thin: gather README/CLAUDE.md/PLAYGROUND surfaces + real collected count, gate + report → sigma/docs-check.md; powers `sigma docs-check --check`
cli/session_context.py  pure: build_pointer(root) → names ARCHITECTURE.md + .tours/*.tour for a SessionStart hook (lazy /learn hint when absent); never raises (read side of learn)
cli/session_hook.py     thin: confirm-gated idempotent install of the SessionStart hook into project .claude/settings.json (immutable merge, like statusline.py)
cli/claude_local.py     pure upsert_block (marker-delimited) + thin write_block into gitignored CLAUDE.local.md — static fallback for the learn pointer
cli/eval.py         pure: parse eval set (markdown cases) + build LM-judge prompt + skeptical parse_grade + aggregate/gate(threshold) + ensure_distinct (SUT≠judge)
cli/eval_run.py     thin: resolve eval set, prompt mode (run SUT → grade w/ distinct judge) or artifact mode, parallel grading fan-out, cost record, write report, --check gate
cli/pipeline.py     execute_stage library (used by hermes/loop): run stage, chain prior artifact, persist; verify reads full chain via chain.json. STAGES includes the two grill GATE stages (grill-blueprint/grill-spec, shared grill template via `template` key + GRILL_TARGET)
cli/weave.py        sigma weave — agent-driven: stage artifacts → chain.html (manifest written first, agent-independent)
cli/weave_manifest.py  pure: build_manifest → chain.json contract + validate_chain_html guard
cli/domains_index.py  pure: resolve each domain → implementer/verifier/logic-evaluator files; powers skills/sigma-domains
cli/loop.py         parse tasks, execute_cycle (maker→checker + logic + optional TDD test-writer + optional post-pass --simplify cleanup w/ re-verify guard + optional --e2e live-scenario gate), run_loop (sequential or --team parallel)
cli/scenarios.py    pure: parse_scenarios(spec_md) → Scenario(name,given,when,then) list + find_scenario lookup — the BDD Given/When/Then blocks /spec already writes, read back so /e2e + --e2e + /implement-task can drive them live
cli/hermes.py       conductor: route → inject skill → execute_stage → emit event
cli/intent.py       hybrid routing: state-scan default + intent-override classify
cli/skill_map.py    stage → bundled skill mapping; inject_skill into prompts
cli/events.py       append/read events.jsonl — append-only board state spine
cli/board.py        kanban projection (pure build_columns) + rich static/live render
cli/keepawake.py    --keep-awake: caffeinate wrapper, prevents Mac sleep on long runs
cli/checks.py       pure diagnostic probes (python/deps/models/secrets/skills/plugin/config/workspaces/rtk/caveman/statusline/graphify/usage-tool/codex-login); run_all()'s `usage_which` param is dedicated to check_usage_tool, deliberately NOT reusing the `which` param check_models/check_model_auth already use (different lookup semantics — model CLIs vs. node runtime)
cli/doctor.py       sigma doctor — run checks, confirm-gated fixes, --check/--yes/--update (dual-surface: CLI git pull + plugin update)
cli/onboard.py      sigma onboard — first-run setup: domains, API keys, sign-in guide, codex login, RTK, caveman, ccstatusline, graphify, SessionStart hook, + offer to build learn artifacts (step 11, confirm-gated, no-op if they exist; learn_fn injectable so tests never spawn an agent)
cli/codex_login.py  detect/prompt ChatGPT sign-in for the codex CLI (`codex login`, confirm-gated, RTK-shaped) — powers research's gpt lane + `loop --codex-verify`/`--codex-tdd`; distinct from the OPENAI_API_KEY secret (codex exec doesn't use it)
cli/uninstall.py    pure build_plan (launcher/~/.sigma/plugin surfaces) + run_uninstall (confirm-gated, separate .env-secrets confirm, best-effort, injectable I/O); leaves global RTK/caveman/statusline
cli/setup_repo.py   one-shot per-repo bootstrap: composes config + session_hook + claude_local + learn + claude_md (config-if-missing → hook idempotent → CLAUDE.local → map unless --no-learn / artifacts exist → CLAUDE.md scaffold-if-missing/check-if-present unless --no-claude-md); learn_fn/claude_md_scaffold_fn/claude_md_check_fn all injectable (tests never spawn an agent)
cli/claude_md_check.py  pure: deterministic checks (length vs ~200/300-line thresholds, pasted-code-block/@import/stale-test-count/placeholder detection) + qualitative agent-prompt/parse reusing review.Finding + review's FINDING grammar and CRIT/HIGH gate
cli/claude_md_check_run.py  thin: real pytest --collect-only count, runs both layers on CLAUDE.md (required) + CLAUDE.local.md (optional, skipped if absent), writes sigma/claude-md-check.md
cli/claude_md_scaffold.py  pure: WHAT/WHY/HOW skeleton + agent prompt for a best-practice CLAUDE.md ("repo") or CLAUDE.local.md ("local") — distinct from native /init (no length/structure discipline there)
cli/claude_md_scaffold_run.py  thin: drives the scaffold agent, falls back to the static skeleton on failure/empty output, refuses to overwrite an existing file without --force
cli/secrets.py      ~/.sigma/.env key store (chmod 600) — never the committed config
cli/rtk.py          detect/install/activate RTK token-saver (confirm-gated, idempotent)
cli/caveman.py      detect/install caveman terse-output mode (confirm-gated, RTK-shaped)
cli/statusline.py   detect/configure ccstatusline status line (confirm-gated; writes settings.json statusLine, preserves other keys)
cli/render.py       σ logo + update banner + rich/plain check output + confirm prompt
cli/gate.py         wakeAgent gate — cheap pluggable pre-check, skip work (0 tokens)
cli/skills_index.py topic-key + contradiction detection across ratcheted skills
cli/skills_recall.py  pure: recall_lessons(skills_dir, domain) + render_recall_block — read side that closes the learning loop
cli/review.py       pure: change-set parse, domain infer, 3-axis prompt build, finding parse/aggregate/dedup, gate (fail on CRIT/HIGH or inconclusive axis), distinct-axis guard
cli/review_run.py   thin: resolve change set (git diff / gh pr diff), parallel 3-axis fan-out, write report, PR comment, ratchet CRIT/HIGH → skills/, record cost; appends the graph-impact section when graph.json present
cli/graph_impact.py pure: read graphify graph.json (stdlib, never import) → per-changed-file touched nodes + reverse-edge dependents; powers sigma review's informational Impact section
cli/profile_manifest.py  pure: logic-profile skeleton + validate (both sections) + staleness(profile, files) banner
cli/profile_run.py  thin: AgentRunner walker → sigma/profile/logic-profile.md (ML-logic + system-logic invariants)
cli/cost.py         pure: estimate(op,units) + model-tier routing + calibrate from ledger + record contract + report; fail-safe to static factors
commands/           slash-command templates (one per stage + /craft + /grill + /grill-loop + /learn + /scout + /prune + /weave + /profile + /review + /eval + /e2e + /sigma-learn-lesson), YAML frontmatter
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
- **Release checklist**: every version bump (`cli/__init__.py` +
  `.claude-plugin/plugin.json`) MUST land in the SAME change as a README.md
  update — new commands, new modules under `## 📦 What's inside`/`## ⚙️ The
  CLI`, and the pytest count if it changed. CLAUDE.md gets the same treatment
  (Commands section, Layout table, new Gotchas). A version bump with no
  README/CLAUDE.md diff is a signal something was missed, not a smaller diff.

## Gotchas

- `sigma research`'s real synthesis (`cli/research.py`'s `synthesize`) runs on
  `claude_synthesis_runner` by default — a real `run_model("claude", prompt)`
  call, unrouted (always the CLI default model, not the `TIER_STRONG` tier
  `cli/cost.py`'s `routing_for("research")["synthesis"]` provisions). That key
  IS consumed now: `cmd_research` routes synthesis to the strong tier by
  default via `routed_synthesis_runner` (claude adapter `model_alias`
  passthrough); `--no-route` restores the unrouted `claude_synthesis_runner`.
  A failed/unavailable claude CLI degrades to the static placeholder text
  (fail-safe), never crashes the run.
- The in-session `/research` command's claude lane invokes a `deep-research`
  skill IF ONE IS AVAILABLE in the session (sigma does not vendor/ship one —
  it's a conditional capability check, not a guarantee). A clean
  `/plugin install sigma@sigma` with no external deep-research skill loaded
  falls back to MCP search-tool dispatch + the model's own reasoning, with an
  explicit "no such skill available" note — never a silent substitution.
- Search-tool fan-out (`run_research`'s `tool_futures`) passes the BARE
  `topic` string to `search_runner`, never the full LLM brief `build_prompt`
  produces — a search API query is not a chat instruction paragraph. Only the
  model-CLI fan-out (`model_futures`) gets the full brief.
- Firecrawl deep-crawl (`run_search_tool`'s `deep` param) fires ONLY when
  `run_research`'s own `deep` flag is set — `web=True` alone does NOT trigger
  scraping on the search-tool tier (unlike the model-CLI tier, where
  `web_search = deep or web`). Scraping is a real extra HTTP call per URL, so
  it's gated to the exhaustive `--deep` path only. Top-3 result URLs are
  deduped (`dict.fromkeys`) before scraping — a duplicate URL in the top N
  (e.g. canonical + mirror) is scraped once, not twice. Scraped markdown is
  capped at `_SCRAPE_TEXT_CAP` chars with a truncation notice (mirrors
  `cli/graphify.py`'s `report_block` cap) — unbounded page content would
  otherwise bloat `research.md` and the downstream synthesis prompt. A
  per-URL scrape failure degrades that item to snippet-only; never aborts the
  call. `deep=False` issues zero scrape calls — byte-identical to pre-deep-crawl
  output (regression-locked by test).
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
- **Two learn paths, two OUTPUT contracts — don't cross them.** The CLI (`sigma
  learn`, `cli/learn.py`'s `LEARN_INSTRUCTIONS`) tells the agent to EMIT
  `=== ARCHITECTURE.md ===` / `=== TOUR.json ===` blocks to stdout; the CLI
  captures that stdout, `split_output` parses the headers, and the CLI writes the
  files. That contract ONLY works because a subprocess wrapper reads the output.
  The plugin path (`commands/learn.md`, `/sigma:learn`) has NO wrapper — it runs
  in-session, so it must instruct the agent to **Write the files directly** (like
  every sibling command: spec/propose/weave). It previously reused the CLI's
  emit-to-stdout format, so `/sigma:learn` printed the map into chat and wrote
  nothing (`commands/learn.md` was the only command with `=== header` blocks).
  Fixed: the command now says "Write both files with the Write tool". The two
  paths stay decoupled — the CLI never reads `commands/learn.md`.
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
  model-ID map to drift); routing is ON BY DEFAULT on `loop` (`--no-route` opts
  out; `--route` is a deprecated no-op) and per-STAGE on `hermes`
  (`routing_for("hermes")`: planning/grill stages→strong, execution→mid —
  resolved AFTER `intent.route` picks the stage via `_stage_runner`; the
  intent-classification runner stays unrouted); `eval` keeps opt-in `--route`. `trajectory_sink` is a best-effort `Callable[[dict], None]`
  called once per run — a failing sink is SWALLOWED (observability must never break a
  run, the inverse of a hard gate). `AgentRunner.run` gained a `role=` label
  (default `"agent"`); loop/hermes pass it (implementer/verifier/logic/test-writer/
  eval-sut/eval-judge) so the trajectory can attribute steps. Test fakes that
  subclass AgentRunner must accept `role=` in their `run` signature.
- `cli/trajectory.py` (pure, like `events.py`) appends one step per agent run to
  `trajectory.jsonl` in the workspace; caller passes `ts` (no clock in the pure
  path). `summarize` is a deterministic projection. `sigma trajectory --topic <t>`
  renders it. Missing file → empty (lenient read-model). Git-ignored (derived).
- `sigma trajectory --economy` (`cli/axis_economy.py` pure) joins tokens-per-axis
  with did-that-axis-produce-value, one level finer than `--efficiency`'s run total.
  Two projections over the SAME `trajectory.jsonl`: non-cycle steps → tokens + run
  count per role (REAL telemetry only — a role with no measured tokens is
  "unmeasured", NEVER estimated; that guess lives in `sigma cost`); `role="cycle"`
  steps → per-axis value events via `_VALUE_FIELD` (logic/e2e EARN by CATCHING a fail
  the code checker missed → flag is `False`; advisor/simplifier/test-writer by
  SUCCEEDING → flag is `True`). `record_cycle_steps` stamps those effect flags onto
  each cycle step (T2); `TrajectoryStep`/`build_step` gained the five `Optional[bool]`
  fields (lenient — a pre-effect-fields trajectory reads with them all None, so old
  files still parse). `implementer`/`verifier` are CORE (always earn, never flagged).
  Flagging follows the prune law: an axis is a candidate only when
  `not is_core AND measured AND token_total > 0 AND value_events == 0` — the `measured`
  check MUST precede `token_total > 0` because an unmeasured axis has
  `token_total=None` and `None > 0` raises `TypeError` (regression-locked by
  `test_unmeasured_zero_value_axis_does_not_raise_on_flag_check`). Zero tokens AND zero
  value → NOT flagged (never act on absent evidence). SURFACE-only, never
  auto-disabled; run-scoped wording ("0 value events in this run", not "useless").
  `--json` emits the `AxisEconomy` via `asdict`. Fail-safe: empty/missing → "no data
  yet", never raises.
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
- `loop --e2e` adds a DISTINCT E2E RUNNER agent that drives a task's mapped BDD
  scenario LIVE (Given/When against a running instance of the app, then checks
  Then). Scenarios come from `cli/scenarios.py`'s `parse_scenarios(spec.md)` —
  `cmd_loop` parses spec.md ONCE up front and passes the list to every cycle
  (`execute_cycle` never re-reads the file). A task maps to a scenario via a
  `[scenario: <name>]` tag on its `tasks.md` line (`Task.scenarios`, parsed by
  the SAME `TASK_RE` that reads id/domain); no tag → the axis is SKIPPED
  entirely (`CycleOutcome.e2e_ok` stays `None`), not scored. Three-way verdict —
  `_e2e_verdict` returns PASS/FAIL/ERROR, defaulting to ERROR (not FAIL) when no
  `VERDICT:` line is found, because a crashed/timed-out e2e run produced no real
  verdict at all — that is categorically different from a clean run whose
  assertion was false. This is the INVERSE of `_verdict_pass`'s skeptical
  default-FAIL: here, absent evidence must never masquerade as a scored failure
  (same law `sigma prune` follows for unused-tool evidence). GATE semantics: a
  `FAIL` blocks the cycle and ratchets (`ratchet_to_skills` with prefix
  `"e2e failed:"`, distinct from `"verify failed:"` so the two failure modes
  never share a `topic_key` and falsely flag each other as contradictions); an
  `ERROR` never flips a passing cycle to FAIL and is never ratcheted — logged to
  `outcome.notes` only. Enforced distinct from
  implementer/verifier/logic/test-writer/simplifier/advisor via the same
  `is`-identity `ValueError` chain. Runs AFTER verify(+logic) pass but BEFORE the
  advisor-escalation decision, so an e2e FAIL on an otherwise-passing verify
  still gets a chance at advisor rescue — `_run_advisor_escalation` re-runs BOTH
  verify and (when `e2e_runner` is given) the e2e check each retry round,
  resetting `outcome.e2e_ok` to `None` at the top of each round so a round whose
  failure is a verify/logic regression doesn't carry a stale e2e verdict from a
  prior round. `--e2e` routes to the `TIER_STRONG` tier under `--route` (same as
  `logic` — judging a live Then assertion needs full reasoning, not the
  mechanical tier). `/e2e` (plugin-only slash command, no Python backing) runs
  every scenario in spec.md on demand; `/implement-task` runs the per-task
  check inline after its TDD step. All three surfaces share the same
  spec.md-is-the-source-of-truth scenario format — no separate scenario file.
- **CLI-default vs library-default are DIFFERENT layers.** `execute_cycle`'s
  `logic_checker`/`simplifier`/`advisor`/`e2e_runner` params still default to
  `None` at the pure-logic layer (unchanged — a bare `execute_cycle()` call is
  still byte-identical to before any axis existed). What changed is `cmd_loop`'s
  CLI wiring: `--logic`/`--simplify`/`--advisor`/`--e2e` now default to `True`
  in argparse (`--no-logic`/`--no-simplify`/`--no-advisor`/`--no-e2e` opt out),
  so a bare `sigma loop --execute` runs all four correctness/cleanup axes.
  `--tdd`/`--team` stayed opt-in (default `False`) — they change the execution
  MODEL (test-first workflow, worktree parallelism), not just add a check, so
  flipping them by default would be a bigger surprise than adding a check.
  `--all` is CLI-only sugar that flips ALL SIX (including tdd/team) to `True`
  inside `cmd_loop`'s body, applied AFTER parsing (`args.all` is read once, then
  the six attrs are overwritten) — it is not itself a `run_loop`/`execute_cycle`
  parameter.
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
- `sigma review` appends an informational **Impact** section from graphify's
  `graph.json` when present (`cli/graph_impact.py` → `review_run`): per changed file,
  the nodes it defines + reverse-edge dependents. Purely additive — the gate and axis
  prompts are UNTOUCHED, and no graph → report byte-identical to before (regression-
  locked by `test_review_report_byte_identical_without_graph`). Schema-tolerant parsing
  (tries nodes/edges|links, source/target|from/to endpoints, file|path|source|source_file
  node paths, name|label|id names; ends-with match handles abs-vs-relative paths),
  fail-safe to empty; the append is wrapped in try/except so it never breaks a completed
  review. sigma NEVER imports graphify (reads the file directly, stays 3.9).
- `setup_graphify_hook` (`cli/graphify.py`) wires graphify's OWN `graphify hook install`
  (post-commit graph refresh, AST-only 0-cost, + a graph.json git merge driver) — sigma
  does NOT author its own hook. Confirm-gated + idempotent (setup_graphify shape): no
  graphify binary → no-op; hook already present → no-op. `graphify_hook_status` greps
  `.git/hooks/post-commit` for a `graphify` marker (fail-safe: no .git/unreadable →
  not-installed). Onboard step 9b + `check_graphify_hook` (WARN-never-FAIL, gated on the
  graphify binary). `_default_spawn` gained an optional `cwd` so the install runs in the
  repo (existing one-arg callers unaffected).
- `--codex-verify`/`--codex-tdd` (loop) run the verifier/test-writer role through
  the `codex` CLI instead of `claude` — a genuine cross-provider maker≠checker
  check (not just cross-prompt). Built on `AgentRunner`'s new `argv_builder`/
  `output_cleaner` hooks (`cli/runner.py`) — `argv_builder` replaces the
  claude-shaped `[-p, --model, prompt]` argv entirely (codex's shape is
  `exec --sandbox <mode> --color never <prompt>`, no `-p`); `output_cleaner`
  strips codex's session-metadata preamble (reuses `cli/models.py`'s
  `clean_output("gpt", ...)`) so `VERDICT:` parsing isn't corrupted by
  `workdir:`/`tokens used:` lines. Sandbox is role-specific: verifier is
  `read-only` (a checker must never mutate), test-writer is `workspace-write`
  (it writes a real failing-test file). `--codex-tdd` without `--tdd` is a
  usage error (the test-writer role doesn't exist outside TDD mode).
  Deliberately excluded from `--all` — codex needs a second CLI + its own
  `codex login` auth the user may not have set up (`cli/checks.py`'s
  `check_model_auth` already surfaces the login hint for research's gpt lane;
  same login covers this), so bundling it into `--all` would risk silently
  degrading every cycle to `codex CLI not found`. `--model` tier routing does
  NOT apply to codex-backed roles — codex has no alias-passthrough `--model`
  contract like claude's, so `codex_argv_builder` ignores the `model` arg it's
  passed (ModelAdapter reuse via `cli/models.py`'s `ADAPTERS["gpt"].build_argv`,
  not a separate codex adapter).
- `cli/codex_login.py` (mirrors `cli/rtk.py`'s shape exactly: `codex_login_status`
  + confirm-gated `setup_codex_login`) turns the passive login HINT above into an
  ACTIVE offer — `sigma onboard` (step 5b, right after the model-auth hint) and
  `sigma doctor`'s `check_codex_login` fix both spawn the real interactive
  `codex login` (opens a browser) when the user confirms. `logged_in` requires
  BOTH exit code 0 AND `"logged in"` in `codex login status`'s stdout (lowercased
  match) — an unrecognized future CLI message defaults to not-logged-in, the
  conservative read (same direction as gate-defaults-WAKE is NOT: here absence of
  positive evidence means "prompt again", not "assume done"). Not installed →
  no-op, no prompt (nothing to log into) — same idempotent shape as RTK/caveman.
  Distinct from the `OPENAI_API_KEY` secret onboard's step 4 already captures —
  `codex exec` is ChatGPT-subscription-backed and never reads that key; the two
  coexist in onboard for unrelated reasons (OPENAI_API_KEY predates codex and may
  serve other future openai use, not consumed by any current sigma code path).
- Telemetry (`cli/telemetry.py` + `AgentRunner(telemetry=True)`) parses the
  `claude -p --output-format json` result envelope: output becomes the agent's
  final text and the trajectory step carries MEASURED tokens/cost. Fail-safe:
  a malformed envelope degrades to the raw-text path; codex-shaped runners
  (`argv_builder` set) are never touched. `cmd_loop` sums a run's real tokens
  via `trajectory.counting_sink` and appends an actuals row to
  `sigma/costs.jsonl` — zero measured tokens → no row (never a fake actual).
- `sigma lessons` follows prune's laws: zero recall-carrying cycle steps → NO
  archive candidates (never act on absent evidence); `--archive` MOVES a lesson
  to `skills/archive/` (confirm-gated per lesson, reversible) — recall +
  `list_domain_lessons` both exclude `archive/`. "Not working" lessons
  (recalled but cycles keep failing) are surfaced for a human rewrite, never
  auto-edited.
- `sigma eval --from-spec <topic>` renders spec.md scenarios into
  `sigma/evals/<slug>.md` via the pure, deterministic
  `scenarios.render_eval_set` (Given/When → case input, Then → rubric — the
  round-trip through `eval.parse_eval_set` is regression-locked). The set is
  DERIVED; spec.md stays the source of truth; refuses overwrite without
  `--force`.
- The verify + logic prompts receive a task's mapped BDD scenario(s) as
  acceptance criteria (`loop._scenario_context`) — `cmd_loop` parses spec.md
  regardless of `--e2e` now. No mapped scenario → prompts byte-identical
  (regression-locked), same fail-safe law as `_with_recall`.
- `claude_md_check`/`claude_md_scaffold` NEVER auto-edit an existing CLAUDE.md —
  check surfaces findings, scaffold refuses to overwrite without `--force`. This
  file's own first real run scored a HIGH (676 lines, past the ~300-line ceiling
  the research it's built from documents) — a live demonstration the tool works,
  not yet acted on. `check_imports` resolves `@path` relative to the FILE, not
  cwd, per official docs; `check_test_count_claims` skips (never guesses) when
  `real_test_count` is `None`.
