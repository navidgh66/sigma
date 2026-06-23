<div align="center">

# σ · sigma

**A portable, spec-driven, loop-engineered AI workflow toolkit for data science & AI engineering.**

*Clone once. Works in every repo. You design the loop — the loop does the work.*

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-419%20passing-brightgreen.svg)](tests/)
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
> loops that prompt your agents." — [Addy Osmani](https://addyosmani.com/blog/loop-engineering/)

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
  cycles; `--tdd` writes the failing test first; `--team` runs independent tasks
  in parallel; `--logic` adds a reasoning axis. `hermes --auto` chains whole
  stages until a human gate.
- **🎛️ Lean context** — only the domain a task needs is loaded, surfaced
  in-session by the `sigma-domains` skill.

---

## 🚀 Quick start

```bash
# install (global) — σ banner + staged setup
curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh
export PATH="$PATH:$HOME/.local/bin"

# friendly first run: pick domains, capture API keys, optional RTK / status line
sigma onboard
```

Then, **inside Claude Code**, add the plugin and go:

```text
/plugin marketplace add navidgh66/sigma
/plugin install sigma@sigma

/research "your topic"   →   /propose   →   /blueprint   →   /grill
/spec   →   /grill   →   /tasks   →   /implement-task   →   /verify   →   /loop
```

`sigma doctor` health-checks and repairs the install anytime; `sigma doctor
--update` refreshes both the CLI and the plugin in one shot.

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
/implement-task  build one task with its domain context loaded (reuse-first)
      ↓
/verify          domain checks + BDD scenario coverage (separate checker agent)
      ↓
/loop            autonomous: discover → implement → verify → ratchet failures
```

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
sigma research "topic" --deep   # exhaustive web-grounded multi-model brief
sigma loop --topic <t> --execute --team --tdd --logic   # autonomous, parallel, test-first
sigma hermes "build it" --topic <t> --auto              # chain stages to a human gate
sigma board --topic <t> --watch                         # live kanban over agent progress
sigma weave --topic <t>                                 # artifacts → chain.html + chain.json
sigma review <PR#|url>                                  # 3-axis team-change review
sigma profile                                           # codebase logic invariants → profile
sigma doctor --update                                   # refresh CLI + plugin, then health-check
```

**Two ways to run, by design:**
- **Plugin (primary)** — stages run *in-session* as slash commands; they load the
  domain context and stay steerable. This is where the work happens.
- **CLI (escape hatch)** — parallel `research`, autonomous `loop`/`hermes`, live
  `board`/`weave`, and setup (`onboard`/`doctor`). For when you want to walk away.

---

## 🧩 Skills that auto-surface

| Skill | Does |
|-------|------|
| `sigma-domains` | loads the right domain context-engine for the task |
| `sigma-lessons` | recalls past ratcheted lessons by domain |
| `sigma-grilling` | the adversarial grilling rubric (powers `/grill`) |
| `sigma-grill-loop` | the bounded auto-grill loop (powers `/grill-loop`) |
| `sigma-present` | exports an artifact to a single-file HTML deck / report |
| `sigma-cost` | estimates + routes token cost for heavy ops |

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

- **402+ pytest tests, ruff-clean** — pure logic (config, routing, parsing, board
  projection, cost) is separated from subprocess execution and fully tested with
  fakes. No real agent is spawned in the test suite.
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

MIT © Navid Ghayazi

<div align="center">
<sub>Built on <a href="https://docs.anthropic.com/claude-code">Claude Code</a> ·
inspired by <a href="https://addyosmani.com/blog/loop-engineering/">Loop Engineering</a>
and the <a href="https://www.anthropic.com/research/building-effective-agents">Anthropic agentic playbook</a>.</sub>
</div>
