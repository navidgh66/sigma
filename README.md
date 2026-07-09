<div align="center">

```
  ███████╗██╗ ██████╗ ███╗   ███╗ █████╗
  ██╔════╝██║██╔════╝ ████╗ ████║██╔══██╗
  ███████╗██║██║  ███╗██╔████╔██║███████║
  ╚════██║██║██║   ██║██║╚██╔╝██║██╔══██║
  ███████║██║╚██████╔╝██║ ╚═╝ ██║██║  ██║
  ╚══════╝╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝
  σ · personal AI workflow toolkit
  created by Navid Ghayazi
```

**A portable, spec-driven, loop-engineered AI workflow toolkit for data science & AI engineering.**

*Clone once. Works in every repo. You design the loop — the loop does the work.*

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-779%20passing-brightgreen.svg)](tests/)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin--first-8A2BE2.svg)](https://docs.anthropic.com/claude-code)
[![Ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)

</div>

---

`sigma` wraps [Claude Code](https://docs.anthropic.com/claude-code) with a
disciplined, research-first pipeline built for the way AI/ML work actually
happens — from classic ML and deep learning to NLP, RL, data engineering, MLOps,
LLM engineering, and AI-agent harness design.

It's **plugin-first**: every pipeline stage is a native slash command, the domain
knowledge and the learning layer are native skills. A thin CLI handles only what
Claude Code can't do in a single session — real parallel multi-model research,
autonomous hands-off runs, a live kanban board, and setup.

> "You shouldn't be prompting coding agents anymore. You should be designing
> loops that prompt your agents."

`sigma` is that loop.

---

## ✨ Why sigma

- **🔬 Multi-model research** — fan out a question to Claude + Gemini + GPT *in
  parallel*, aggregate into one cited `research.md`. Real concurrency, not a
  sequential loop.
- **📋 Spec-driven, BDD-native** — specs carry Gherkin `Scenario / Given / When /
  Then` acceptance criteria that flow as a contract through implement → verify →
  review. No vibe-coding into production.
- **🔥 Adversarial grilling** — a skeptical `/grill` gate pressure-tests the
  blueprint and the spec *before* any code exists. `/grill-loop` auto-drives
  grill → triage → edit → re-grill (mechanical fixes auto-applied, judgment calls
  surfaced). A logic flaw caught here costs a sentence, not a rewrite.
- **🔁 Closed learning loop** — failures ratchet into `skills/` **and are recalled
  by domain on the next run**. The loop doesn't just record mistakes; it stops
  repeating them.
- **🧑‍🔧 Maker ≠ checker, enforced** — implementer, verifier, and the optional
  logic-evaluator are always *distinct* agents. Separation is a `ValueError`, not
  a guideline.
- **🤖 Autonomous when you want it** — `sigma loop --execute` runs maker→checker
  cycles with the **correctness axes ON by default**: a logic-evaluator axis
  (`--no-logic` opts out), a post-pass simplify cleanup (`--no-simplify`), an
  advisor that escalates a fail to a distinct opus-tier agent for a correction
  plan (`--no-advisor`), and a live-scenario gate that drives each task's mapped
  BDD scenario against the running app — a real behavioral FAIL blocks the
  cycle, an unreachable-app ERROR doesn't (`--no-e2e`). Also **routed by model
  tier by default** (mechanical roles → sonnet, logic → opus; `--no-route` opts
  out). `--tdd` (writes the failing test first) and `--team` (independent tasks
  in parallel, each in its own **real git worktree**, merged back on pass,
  conflicts surfaced — never auto-resolved) stay opt-in — they change the
  execution model, not just add a check. `--all` turns on every axis including
  those two. `hermes --auto` chains whole stages until a human gate.
- **🎛️ Lean context** — only the domain a task needs is loaded, surfaced
  in-session by the `sigma-domains` skill. `sigma prune` cuts loaded-but-unused
  MCP servers + plugins that tax every turn.
- **🗺️ Graph-grounded onboarding** — `sigma learn` builds a real dependency graph
  of the repo (via graphify) and grounds its `ARCHITECTURE.md` + CodeTour in
  *extracted* structure, not an eyeball read.
- **🛰️ Self-refreshing bundle** — `sigma scout` discovers skills relevant to your
  domains on skillsmp.com and pulls in the keepers (you approve each one).

---

## 📚 What it's built on

sigma is a synthesis of published practice, not invention — it operationalizes
the playbooks the field already converged on:

- **Anthropic — *Building Effective Agents* & Claude Code best practices** →
  maker ≠ checker separation, distinct verification agents, "give the agent a way
  to verify its work", show-evidence-don't-assert, and the adversarial **`/grill`**
  gate. ([building-effective-agents](https://www.anthropic.com/research/building-effective-agents))
- **Google — agentic SDLC / "factory model"** → the developer's output is the
  assembly line, not the widget; spec-driven stages, intelligent model-tier
  routing, and treating token burn as tracked OpEx (the **cost loop**).
- **Loop engineering** → design loops that prompt agents instead of hand-prompting;
  failures **ratchet** into reusable skills and are recalled on the next run (the
  closed learning loop).
- **TDD & verification literature** → the optional **`--tdd`** axis (failing test
  first, RED→GREEN), the **`verification-before-completion`** discipline, and the
  evidence that *decomposed, independent* checks beat holistic self-review — which
  is why grill scores per-axis and verify uses a distinct agent.
- **Eval-first practice ("set the bar at the eval, not the demo")** → `sigma eval`
  runs eval sets with an LM judge that is always a *distinct* agent from the
  system under test, gated at a pass-rate threshold.
- **Anti-slop refactoring practice** → the **`--simplify`** pass mirrors the
  bundled `/simplify` four-axis cleanup, behaviour-preserving and re-verified.

What's original here is the *integration*: one portable, plugin-first harness that
wires these into a single research → spec → grill → implement → verify → loop
pipeline with a closed learning loop on top.

---

## 🚀 Quick start

```bash
# install (global) — σ banner + staged setup
curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh
export PATH="$PATH:$HOME/.local/bin"

# friendly first run (once per machine): pick domains, capture API keys, optional RTK / status line
sigma onboard

# bootstrap any repo (per repo): config + SessionStart hook + CLAUDE.local + codebase map
sigma setup-repo            # add --no-learn to skip the agent-built map
```

`sigma onboard` is the once-per-machine setup (keys, RTK, caveman, status line,
graphify). `sigma setup-repo` is the per-repo bootstrap — run it in each project to
give it the four local artifacts (`sigma.config.yml`, the SessionStart hook,
`CLAUDE.local.md`, and the `ARCHITECTURE.md` + CodeTour map) so Claude reads that
repo's architecture every session instead of re-exploring. It's idempotent and
never clobbers existing artifacts.

Then, **inside Claude Code**, add the plugin and go:

```text
/plugin marketplace add navidgh66/sigma
/plugin install sigma@sigma

/research "your topic"   →   /propose   →   /blueprint   →   /grill
/spec   →   /grill   →   /tasks   →   /implement-task   →   /verify   →   /loop
```

`sigma doctor` health-checks and repairs the install anytime; `sigma doctor
--update` refreshes both the CLI and the plugin in one shot. To remove sigma,
`sigma uninstall` reverses the installer (launcher + `~/.sigma` + the Claude
plugin), confirm-gated and with a separate warning before deleting your API keys.

---

## 🛠️ The pipeline

```
/research        multi-model parallel search (Claude + Gemini + GPT) → research.md
      ↓
/propose         synthesize → 2-3 approaches with trade-offs + a recommendation
      ↓
/blueprint       pick approach → architecture.md (system design)
      ↓
[ /grill ]       ⛔ adversarial gate — pressure-test the design before code
      ↓
/spec            spec.md — interfaces, schemas, BDD acceptance scenarios
      ↓
[ /grill ]       ⛔ adversarial gate — pressure-test the spec before tasks
      ↓
/tasks           domain-routed task breakdown (waves + dependencies)
      ↓
/implement-task  build one task with its domain context loaded (reuse-first);
                 runs the task's mapped BDD scenario live if tasks.md tags one
      ↓
/verify          domain checks + BDD scenario coverage (separate checker agent)
      ↓
/loop            autonomous: discover → implement → verify → ratchet failures
                 (--e2e adds a live scenario gate per task)
```

`/e2e` runs every BDD scenario in `spec.md` live against the running app —
PASS/FAIL/ERROR per scenario, ratcheting only real FAILs. Callable any time
after `/spec`, and wired into `/implement-task` (per-task) and `sigma loop
--e2e` (per-task gate) so a scenario "covered" by code is also proven to work.

`/grill` is a gate, not a numbered stage — skeptical, maker ≠ griller, **BLOCKs on
a CRITICAL/HIGH logic flaw** (human may override). In the autonomous `hermes
--auto` chain the two gates run as stages and halt at a `grill-blocked` human gate.

Any time, `/weave` folds the stage artifacts into one shareable `chain.html`
(+ a machine-readable `chain.json`).

---

## 🧠 Domains (context-engines)

Each domain ships an `implementers/` + `verifiers/` pack (with a
`logic-evaluator.md`), surfaced in-session by the `sigma-domains` skill.

| Domain | Covers |
|--------|--------|
| `classic-ml` | sklearn, feature engineering, cross-validation, tuning, pipelines |
| `deep-learning` | PyTorch/TF, training loops, CUDA, distributed training, serving |
| `nlp` | Transformers, tokenization, NER/NLU/NLG, fine-tuning, embeddings, RAG |
| `rl` | Gymnasium, PPO/SAC/DQN, reward shaping, multi-agent, RLHF, offline RL |
| `data-analysis` | pandas/polars, EDA, viz, statistical & A/B testing, causal inference |
| `data-engineering` | dbt, Airflow, Spark, Databricks, Delta Lake, data contracts |
| `ai-agent-engineering` | harness design, tool definition, orchestration, evals, MCP |
| `mlops` | MLflow, experiment tracking, model registry, drift detection, CD4ML |
| `llm-engineering` | prompt engineering, RAG, fine-tuning, eval frameworks, agents |

---

## ⚙️ The CLI (power tools + escape hatch)

The plugin is the primary surface; the CLI keeps only what Claude Code can't do
in-session, plus setup:

```bash
sigma research "topic" --deep   # exhaustive web-grounded multi-model brief + real synthesis + optional Firecrawl search tier (scrapes top-3 result pages for full content, not just snippets)
sigma loop --topic <t> --execute --all   # autonomous, parallel, test-first, self-correcting, live-scenario-gated (logic/simplify/advisor/e2e are ON by default even without --all)
sigma hermes "build it" --topic <t> --auto              # chain stages to a human gate
sigma board --topic <t> --watch                         # live kanban over agent progress
sigma weave --topic <t>                                 # artifacts → chain.html + chain.json
sigma review <PR#|url>                                  # 3-axis team-change review (+ graph-impact section when a graphify graph exists)
sigma profile                                           # codebase logic invariants → profile
sigma learn                                             # codebase map → ARCHITECTURE.md + .tour (graph-grounded)
sigma scout                                             # discover relevant skills on skillsmp.com → install on approval
sigma prune                                             # cut loaded-but-unused MCP/plugins → reversible disable
sigma trajectory --topic <t> --efficiency               # real cycle pass rate + escalation rate (measured, not estimated)
sigma usage                                             # real Claude Code token/cache/cost via ccusage (wraps `npx ccusage@latest`)
sigma doctor --update                                   # refresh CLI + plugin, then health-check
```

**Two ways to run, by design:**
- **Plugin (primary)** — stages run *in-session* as slash commands; they load the
  domain context and stay steerable. This is where the work happens.
- **CLI (escape hatch)** — parallel `research`, autonomous `loop`/`hermes`, live
  `board`/`weave`, and setup (`onboard`/`doctor`). For when you want to walk away.

---

## 🗺️ Understand, grow & trim — `learn` · `scout` · `prune`

Three commands keep your codebase understanding and your toolbelt healthy. Each is
also an in-session slash command (`/learn`, `/scout`, `/prune`).

### `sigma learn` — a codebase map grounded in a knowledge graph

```bash
sigma learn                          # → ARCHITECTURE.md + .tours/<slug>.tour
sigma learn --persona "new backend dev"   # tailor the walkthrough to an audience
sigma learn --no-graph               # skip the graph build (plain agent read)
```

An agent reads the repo and emits an onboarding `ARCHITECTURE.md` plus a clickable
CodeTour `.tour`. When **graphify** is installed (offered by `sigma onboard` / the
installer), `learn` first builds a real dependency graph — god-nodes, communities,
call/import edges — and feeds graphify's report into the agent so the map reflects
*extracted* structure. graphify runs in its own isolated environment and sigma just
shells out to it, so the CLI stays Python 3.9 and dependency-light. No graphify? It
degrades to a plain agent read — never an error. `sigma onboard` / `sigma doctor` can
also install graphify's **post-commit hook** (its own `graphify hook install`) so the
graph auto-refreshes on each commit — AST-only, no API cost, with a `graph.json` merge
driver for parallel commits.

### `sigma scout` — keep your skill bundle fresh from skillsmp.com

```bash
sigma scout                          # candidates for your domains, install on approval
sigma scout --recent                 # sort by newly-added (catch trends)
sigma scout --vendor                 # maintainer mode: clone into skills/vendor/
sigma scout --dry-run                # show the ranked table, install nothing
```

Queries [skillsmp.com](https://skillsmp.com) per configured domain, ranks hits by
relevance (domain fit beats raw popularity), drops anything already bundled, and
surfaces the survivors. **Nothing installs automatically** — you confirm each skill
(and check its license) before it's cloned into your project's `.claude/skills/`
(or, with `--vendor`, into sigma's own bundle to commit). An optional free
`SKILLSMP_API_KEY` in `~/.sigma/.env` raises the daily rate limit.

### `sigma prune` — cut unused MCP/plugin context bloat

```bash
sigma prune                          # surface loaded-but-unused items → confirm each
sigma prune --check                  # read-only; exit 1 if prunable bloat exists (CI)
sigma prune --yes                    # disable all prunable plugins without prompting
```

Every enabled plugin and connected MCP server injects its tool schemas into *every*
Claude turn. `prune` inventories what's loaded, estimates each item's context
weight, scans recent transcripts for what you actually used, and ranks the
loaded-but-unused heaviest-first. Disabling is **reversible** (flips
`enabledPlugins` off in `settings.json`, every other key preserved — never an
uninstall) and **never guesses**: with no usage evidence it prunes nothing.

> Hygiene trio: **scout grows** the bundle, **prune trims** it, **`sigma cost`
> sizes** it — orthogonal to RTK (proxy tokens) and caveman (output terseness).

---

## 🧩 Skills that auto-surface

| Skill | Does |
|-------|------|
| `sigma-domains` | loads the right domain context-engine for the task |
| `sigma-lessons` | recalls past ratcheted lessons by domain |
| `sigma-grilling` | the adversarial grilling rubric (powers `/grill`) |
| `sigma-grill-loop` | the bounded auto-grill loop (powers `/grill-loop`) |
| `sigma-present` | exports an artifact to a single-file HTML deck / report |
| `sigma-docs` | README / API-reference / CHANGELOG / presentation for external audiences |
| `sigma-cost` | estimates + routes token cost for heavy ops |
| `sigma-scout` | curation rubric for `sigma scout` (relevance + license vetting) |
| `sigma-prune` | pruning rubric — disable ≠ delete, never prune on absent evidence |

---

## 🎯 Principles

- **Loop engineering** — design the loop, stay the engineer. Failures ratchet into
  permanent, recalled knowledge.
- **Maker ≠ checker** — the agent that builds never grades itself.
- **Skeptical by default** — a missing `VERDICT: PASS` is a FAIL; a missing grill
  `VERDICT: READY` is a BLOCK. Silence is never a pass.
- **Reuse-first** — a laziness ladder (YAGNI → reuse → stdlib → native → installed
  → one-liner → only then new code) before any line is written.
- **YAGNI** — no dashboards or telemetry until the single-user core proves out.

---

## 📦 What's inside

- **779 pytest tests, ruff-clean** — pure logic (config, routing, parsing, board
  projection, cost, graph/scout/prune, git worktrees, BDD scenario parsing) is
  separated from subprocess execution and fully tested with fakes (worktree/merge
  logic is tested against real temp git repos). No real agent, network, or
  settings file is touched in the CLI-behavior test suite.
- **Plugin-first** — `commands/*.md` are native slash commands; `skills/*` are
  native skills; `.claude-plugin/` makes it a one-command marketplace install.
- **Dependency-light** — standard library first; `pyyaml` + `rich` at runtime.
- **Python 3.9 target** — runs on the version you already have.

---

## 🎮 Playground

New here? [`docs/PLAYGROUND.md`](docs/PLAYGROUND.md) is a hands-on tour of every
command and feature with copy-paste examples and expected output.

---

## 📄 License

MIT

<div align="center">
<sub>Built on <a href="https://docs.anthropic.com/claude-code">Claude Code</a> ·
inspired by loop-engineering principles
and the <a href="https://www.anthropic.com/research/building-effective-agents">Anthropic agentic playbook</a>.</sub>
</div>
