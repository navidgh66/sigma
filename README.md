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
[![Tests](https://img.shields.io/badge/tests-665%20passing-brightgreen.svg)](tests/)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin--first-8A2BE2.svg)](https://docs.anthropic.com/claude-code)
[![Ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)

</div>

---

`sigma` wraps [Claude Code](https://docs.anthropic.com/claude-code) with a
disciplined, research-first pipeline built for the way AI/ML work actually
happens — from classic ML and deep learning to NLP, RL, data engineering, MLOps,
LLM engineering, and AI-agent harness design.

It's **plugin-first**: every pipeline stage is a native slash command, the domain
knowledge and the learning layer are native skills, and the loop runs in your
session with its own role agents and a Stop-hook guard. A thin CLI handles only
what Claude Code can't do in a single session (real parallel multi-model
research) plus setup and hygiene.

> "You shouldn't be prompting coding agents anymore. You should be designing
> loops that prompt your agents."

`sigma` is that loop.

---

## 🆕 What's new

- **0.31.0**: every command, agent, skill and domain guide was audited against the
  Opus 5.5 prompting guide. `/craft` gives a one-line update per stage and a recap;
  `/research` gives its parallel lanes a time budget; `/verify` dispatches the
  read-only `sigma-verifier` agent. Domain guides now teach structured outputs,
  `strict` tools, and the request params that return 400 on Opus 5.5. The claude
  research lane can use WebSearch/WebFetch in `--web`/`--deep` mode.
- **0.30.0** — research is **Claude + Codex** only (Gemini removed; old configs
  that list it still load). Codex sign-in uses the **device-code flow**
  (`codex login --device-auth`). `sigma doctor --update` now says clearly when
  the CLI could not update, and shows the version actually on disk.
- **0.29.0** — caveman removed; sigma no longer installs, checks or bundles it.
- **0.28.0** — the in-session `/loop` (role agents, Stop-hook guard, test tamper
  guard, capped lesson recall) replaced the old CLI loop engine; built on the
  Opus 5.5 prompting guide.

Full notes: [releases](https://github.com/navidgh66/sigma/releases).

---

## ✨ Why sigma

- **🔬 Multi-model research** — fan out a question to Claude + GPT (via codex) *in
  parallel*, aggregate into one cited `research.md`. Real concurrency, not a
  sequential loop.
- **📋 Spec-driven, BDD-native** — specs carry Gherkin `Scenario / Given / When /
  Then` acceptance criteria that flow as a contract through implement → verify →
  review. No vibe-coding into production.
- **🔥 Adversarial grilling** — a skeptical `/grill` gate pressure-tests the
  blueprint and the spec *before* any code exists. `/grill-loop` auto-drives
  grill → triage → edit → re-grill (mechanical fixes auto-applied, judgment calls
  surfaced). A logic flaw caught here costs a sentence, not a rewrite.
- **🔁 A loop that finishes** — `/loop` runs every open task to done in your
  session. Each task gets a distinct `sigma-implementer` and a read-only
  `sigma-verifier` that must run the tests itself and quote the evidence. A
  plugin **Stop hook** reads `loop-state.json` and sends the session back to work
  while tasks are open and nothing blocks them (at most 3 nudges without
  progress), because a text-only end of turn is a report, not proof the work is
  done (the Opus 5.5 guide's unattended-run pattern).
- **🧑‍🔧 Maker ≠ checker, by tool permission** — the verifier and e2e agents have no
  Edit/Write tools, and a **test tamper guard** fails any attempt that edits or
  deletes a pre-existing test. Agents edit tests to pass when merely told not to;
  sigma checks it structurally.
- **🧪 Proven live, not just covered** — tasks tagged `[scenario: ...]` get a
  `sigma-e2e` agent that drives the spec's BDD scenario against the running app
  (PASS/FAIL/ERROR; an unreachable app is ERROR, never a scored FAIL).
- **🔁 Closed, capped learning loop** — a task that fails its retries ratchets a
  lesson into `skills/`; the next run recalls the **5 newest** for that domain.
  Small on purpose: big skill libraries measurably make agents pick the wrong one.
- **🛠️ Bring your own design** — already have a design, plan, or big spec?
  `/craft` drives `spec → grill → tasks → loop` to verified code, skipping the
  `research → propose → blueprint` front half. Same human gates: grill BLOCK,
  spec approval, a failed task.
- **🎛️ Lean context** — only the domain a task needs is loaded, surfaced
  in-session by the `sigma-domains` skill. `sigma prune` cuts loaded-but-unused
  MCP servers + plugins that tax every turn; `sigma docs-check` keeps version and
  test-count claims honest across the docs.
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
  assembly line, not the widget; spec-driven stages, model-tier and effort
  routing, and treating token burn as tracked OpEx (the **cost loop**).
- **Loop engineering** → design loops that prompt agents instead of hand-prompting;
  failures **ratchet** into reusable skills and are recalled on the next run (the
  closed learning loop).
- **TDD & verification literature** → the optional test-first mode (a distinct
  `sigma-test-writer` writes the failing test, RED→GREEN), the **`verification-before-completion`** discipline, and the
  evidence that *decomposed, independent* checks beat holistic self-review — which
  is why grill scores per-axis and verify uses a distinct agent.
- **Anthropic — *Prompting Claude Opus 5.5*** → the in-session `/loop`: a
  checklist the model updates, text-only turn ends treated as reports, capped
  automatic continuations, the named early stops to avoid, per-role `effort`
  instead of "think harder" lines, evidence instead of written-out reasoning, and
  marking pasted text. ([guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5))
- **2025-26 agent research** → tests protected from the implementer (agents edit
  tests even when told not to), checkers that must run code, and a small capped
  lesson recall (large skill libraries and long context files cost more than they
  help).

What's original here is the *integration*: one portable, plugin-first harness that
wires these into a single research → spec → grill → implement → verify → loop
pipeline with a closed learning loop on top.

---

## 🚀 Quick start

```bash
# install (global) — σ banner + staged setup
curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh
export PATH="$PATH:$HOME/.local/bin"

# friendly first run (once per machine): pick domains, API keys, Codex device sign-in, optional RTK / status line
sigma onboard

# bootstrap any repo (per repo): config + SessionStart hook + CLAUDE.local + codebase map + CLAUDE.md
sigma setup-repo            # add --no-learn / --no-claude-md to skip either agent step
```

`sigma onboard` is the once-per-machine setup (keys, codex sign-in, RTK, status
line, graphify). `sigma setup-repo` is the per-repo bootstrap — run it in each project to
give it the five local artifacts (`sigma.config.yml`, the SessionStart hook,
`CLAUDE.local.md`, the `ARCHITECTURE.md` + CodeTour map, and CLAUDE.md — scaffolded
if missing, checked against best-practice research if present) so Claude reads
that repo's architecture every session instead of re-exploring. It's idempotent
and never clobbers existing artifacts.

Then, **inside Claude Code**, add the plugin and go:

```text
/plugin marketplace add navidgh66/sigma
/plugin install sigma@sigma

/research "your topic"   →   /propose   →   /blueprint   →   /grill
/spec   →   /grill   →   /tasks   →   /implement-task   →   /verify   →   /loop
```

`sigma doctor` health-checks and repairs the install anytime. To remove sigma,
`sigma uninstall` reverses the installer (launcher + `~/.sigma` + the Claude
plugin), confirm-gated and with a separate warning before deleting your API keys.

### Codex sign-in (device code)

`/research`'s GPT lane runs through the `codex` CLI on your ChatGPT subscription
(no API key). sigma signs in with the device-code flow, which works on a laptop,
over SSH and in cloud sessions alike:

```bash
codex login --device-auth    # prints a URL + one-time code; approve it in any browser
codex login status           # → Logged in using ChatGPT
```

`sigma onboard` and `sigma doctor` offer to run it for you (confirm-gated).

### Updating

```bash
sigma doctor --update        # git pull the CLI (~/.sigma) + update the Claude plugin
sigma --version              # confirm the CLI version
claude plugin list           # confirm the plugin version
```

Restart Claude Code afterwards so the new plugin loads. The CLI and the plugin are
two separate installs; `doctor --update` refreshes both. If it reports
`✗ CLI update failed`, you have local edits in `~/.sigma`:

```bash
git -C ~/.sigma stash && sigma doctor --update
```

### Cloud sessions (Claude Code on the web)

Add sigma to your environment's setup script. The plugin gives you the slash
commands and `/loop`; the CLI needs its own clone and a launcher on a PATH that
non-interactive shells see:

```bash
claude plugin marketplace add navidgh66/sigma || true
claude plugin install sigma@sigma || true
claude plugin marketplace update sigma || true
claude plugin update sigma@sigma || true
[ -d "$HOME/.sigma/.git" ] && git -C "$HOME/.sigma" pull --ff-only -q || git clone -q https://github.com/navidgh66/sigma "$HOME/.sigma" || true
python3 -m pip install -q pyyaml rich 2>/dev/null || python3 -m pip install -q --break-system-packages pyyaml rich || true
printf '#!/usr/bin/env sh\nexec python3 "%s/.sigma/cli/main.py" "$@"\n' "$HOME" > /usr/local/bin/sigma && chmod +x /usr/local/bin/sigma
```

---

## 🛠️ The pipeline

```
/research        multi-model parallel search (Claude + GPT via codex) → research.md
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
/loop            every open task to done: implementer → tamper guard → verifier
                 (→ e2e if tagged), capped retries, lessons on failure; a Stop
                 hook keeps it going until tasks settle

/craft           bring your own design → drives spec → grill → tasks → loop
                 (the back half, in-session; enters mid-pipeline from an artifact)
```

`/e2e` runs every BDD scenario in `spec.md` live against the running app —
PASS/FAIL/ERROR per scenario, ratcheting only real FAILs. Callable any time
after `/spec`, and wired into `/implement-task` and `/loop` (per-task, through
the `sigma-e2e` agent) so a scenario "covered" by code is also proven to work.

`/grill` is a gate, not a numbered stage — skeptical, maker ≠ griller, **BLOCKs on
a CRITICAL/HIGH logic flaw** (human may override). `/craft` stops at the same gate.

To share an artifact, the `sigma-present` skill turns it into a single-file HTML
deck or report.

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
sigma review <PR#|url>                                  # 3-axis team-change review (+ graph-impact section when a graphify graph exists)
sigma profile                                           # codebase logic invariants → profile (grounds review)
sigma learn                                             # codebase map → ARCHITECTURE.md + .tour (graph-grounded)
sigma claude-md-check                                   # check CLAUDE.md + CLAUDE.local.md against best-practice research
sigma claude-md-create --target repo                    # scaffold a best-practice-shaped CLAUDE.md (capped ~200 lines)
sigma docs-check --check                                # version parity + stale test-count claims across the docs
sigma scout                                             # discover relevant skills on skillsmp.com → install on approval
sigma prune                                             # cut loaded-but-unused MCP/plugins → reversible disable
sigma cost                                              # sigma's own heavy-op cost ledger
sigma usage                                             # real Claude Code token/cache/cost via ccusage (wraps `npx ccusage@latest`)
sigma doctor --update                                   # refresh CLI + plugin, then health-check
```

**Two ways to run, by design:**
- **Plugin (primary)** — stages and `/loop` run *in-session* as slash commands and
  role agents; they load the domain context and stay steerable.
- **CLI** — parallel `research`, `review`/`profile`, and setup + hygiene
  (`onboard`/`doctor`/`learn`/`scout`/`prune`/`docs-check`). The old autonomous
  CLI engine (`loop`, `hermes`, `board`, `weave`) was retired in 0.28.0; `/loop`
  replaces it.

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

After writing the artifacts, `learn` also offers (confirm-gated — it's committed,
shared with your team) a one-line `ARCHITECTURE.md` reference in `CLAUDE.md`, so a
future session or teammate knows to read it. Decline and nothing is touched;
CLAUDE.md is never created or edited without asking first.

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
> sizes** it — orthogonal to RTK (proxy tokens).

---

## 🧩 Skills that auto-surface

| Skill | Does |
|-------|------|
| `sigma-domains` | loads the right domain context-engine for the task |
| `sigma-lessons` | recalls the 5 newest ratcheted lessons for a domain |
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
- **Evidence over claims** — checkers run the tests and quote the output; a text
  report is never proof the work is done.
- **Reuse-first** — a laziness ladder (YAGNI → reuse → stdlib → native → installed
  → one-liner → only then new code) before any line is written.
- **YAGNI** — every harness piece encodes an assumption about what the model can't
  do; when a newer model makes one unnecessary, remove it (0.28.0 cut ~3,800
  lines this way).

---

## 📦 What's inside

- **665 pytest tests, ruff-clean** — pure logic (config, research routing, parsing,
  lesson ratchet + recall, the Stop-hook decision, the tamper guard, cost,
  graph/scout/prune) is separated from subprocess execution and tested with fakes.
  No real agent, network, or settings file is touched by the suite.
- **Plugin-first** — `commands/*.md` are native slash commands; `agents/*.md` are
  the `/loop` role agents; `hooks/hooks.json` registers the loop guard; `skills/*`
  are native skills; `.claude-plugin/` makes it a one-command marketplace install.
- **Dependency-light** — standard library first; `pyyaml` + `rich` at runtime; the
  hook and tamper guard are stdlib-only scripts.
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
