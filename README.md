# σ sigma

> **Personal AI workflow toolkit for data science & AI engineering.**
> Clone once. Works everywhere. Research-first, spec-driven, loop-engineered.

`sigma` is a portable, composable workflow system that wraps Claude Code with a
disciplined pipeline built for data scientists and AI engineers — from classic ML
to deep learning, NLP, reinforcement learning, data engineering, MLOps, LLM
engineering, and AI-agent-harness engineering.

It is inspired by 
[Loop Engineering (Addy Osmani)](https://addyosmani.com/blog/loop-engineering/),
the [Anthropic agentic playbook](https://www.anthropic.com/research/building-effective-agents),
and meta-harness ideas from OmniGent.

---

## Philosophy

> "You shouldn't be prompting coding agents anymore. You should be designing
> loops that prompt your agents." — Addy Osmani

`sigma` is that loop. You configure it once and it drives the work; you stay the
engineer — reviewing, steering, and ratcheting failures into permanent knowledge.

---

## The Pipeline

```
/research        multi-model parallel search (Claude + Gemini + GPT) → research.md
      ↓
/propose         synthesize research → 2-3 approaches with trade-offs
      ↓
/blueprint       pick approach → architecture.md (system design)
      ↓
/spec            detailed spec.md (interfaces, schemas, acceptance criteria)
      ↓
/tasks           domain task breakdown (which context-engine handles each task)
      ↓
/implement-task  implement one task with its domain context loaded
      ↓
/verify          domain-specific checks (tests, data quality, model eval)
      ↓
/loop            autonomous: discover → implement → verify → ratchet failures
```

Failures (and lessons you capture with `/sigma-learn-lesson`) ratchet into
`skills/` and are **recalled by domain on the next run** — the loop is closed, not
just recorded. Any time, `/weave` folds the stage artifacts into one shareable
`chain.html` (+ a machine `chain.json`).

---

## Domains (context-engines)

| Domain | Covers |
|--------|--------|
| `classic-ml` | sklearn, feature engineering, cross-validation, hyperparameter tuning, pipelines |
| `deep-learning` | PyTorch/TF, training loops, CUDA, distributed training, model serving |
| `nlp` | Transformers, tokenization, NER/NLU/NLG, fine-tuning, embeddings, RAG-adjacent |
| `rl` | Gymnasium, PPO/SAC/DQN, reward shaping, multi-agent RL, RLHF, offline RL |
| `data-analysis` | pandas/polars, EDA, visualization, statistical & A/B testing, causal inference |
| `data-engineering` | dbt, Airflow, Spark, Databricks, Delta Lake, data contracts |
| `ai-agent-engineering` | harness design, tool definition, orchestration, evals, MCP servers |
| `mlops` | MLflow, experiment tracking, model registry, drift detection, CD4ML |
| `llm-engineering` | prompt engineering, RAG, fine-tuning, eval frameworks, agent frameworks |

---

## Install

**Public repo — one-liner:**

```bash
# one command, global — σ logo + staged install
curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh
export PATH="$PATH:$HOME/.local/bin"
sigma onboard       # friendly setup: pick domains, capture API keys, set up RTK
```

**Private repo — clone first, then run the installer:**

`raw.githubusercontent.com` (the `curl | sh` URL) does **not** send your git
credentials, so it 404s on a private repo. Clone with an authenticated account,
then run the bundled installer from the clone — its step 1 sees the existing
`~/.sigma/.git` and just fast-forwards it:

```bash
# authenticate to the account that can see the private repo (gh example)
gh auth login                       # or: gh auth switch --user <account>
gh auth setup-git                   # let git use the gh credential helper

git clone https://github.com/navidgh66/sigma.git ~/.sigma
sh ~/.sigma/installer/setup.sh
export PATH="$PATH:$HOME/.local/bin"
sigma onboard
```

The installer is non-interactive (works under `curl | sh`); the fun part —
choosing domains, entering Gemini/OpenAI keys (stored in `~/.sigma/.env`, never
committed), and optionally installing + activating
[RTK](https://github.com/rtk-ai/rtk) (60-90% token savings) for Claude — happens
in `sigma onboard`. Run `sigma doctor` anytime to health-check and repair the
install.

## Use

```bash
sigma onboard       # first-run: domains, API keys, RTK (interactive)
sigma init          # or just scaffold sigma.config.yml non-interactively
sigma doctor        # diagnose + repair (env, deps, models, skills, plugin, RTK)
sigma               # launch Claude Code with sigma context loaded
```

## Use inside Claude Code (plugin-first)

sigma is **plugin-first**: every stage is a native slash command, and the domain
knowledge + learning layer are native skills — no CLI calls needed for the
in-session flow.

```bash
# public repo: add this repo as a plugin marketplace, then install
/plugin marketplace add navidgh66/sigma
/plugin install sigma@sigma

# private repo: add the LOCAL CLONE as the marketplace instead (no GitHub fetch),
# then install — this is also what installer/setup.sh does automatically:
/plugin marketplace add ~/.sigma
/plugin install sigma@sigma
```

Then in any session:

```
/research <topic>   /propose   /blueprint   /spec   /tasks
/implement-task     /verify    /loop        /hermes  /board   /weave
/sigma-learn-lesson                         # capture a lesson from this session
```

Skills auto-surface as you work:
- **`sigma-domains`** — loads the right domain context-engine for the task.
- **`sigma-lessons`** — recalls past ratcheted lessons by domain.
- **`sigma-present`** — exports an artifact to a single-file HTML deck/report.

**Two ways to run, by design:**
- **Plugin (primary)** — stages run *in-session* as slash commands: they load the
  domain context and stay steerable. This is where the work happens.
- **CLI (power tools + escape hatch)** — only what Claude Code can't do
  in-session: real parallel multi-model `research`, the autonomous `loop`/`hermes`
  runs, live `board`, and `weave`. Plus setup (`onboard`/`doctor`).

---

## Status

✅ **Core + execution + conductor + closed learning loop complete.** All 8
pipeline stages run through a single injectable `AgentRunner`; the loop executes
real maker→checker cycles with distinct agents, writes `impl/` + `verify/`
artifacts, ratchets failures into `skills/`, **and recalls those lessons by domain
on the next run**. 321 tests green, ruff clean. See [`docs/`](docs/).

- **Stages** run in-session as slash commands (`/spec`, `/tasks`, …) — they load
  the matching domain context-engine via the `sigma-domains` skill.
- **`sigma loop --topic <t>`** plans by default; `--execute` runs maker→checker
  cycles (sequential, one workspace). On failure it ratchets a lesson; future
  cycles in that domain recall it.
- **Hermes** (CLI conductor) routes plain language to a stage and runs it:
  `sigma hermes "continue" --topic <t>` (one hop) or `--auto` (chain to a human
  gate). The loop adds an optional **logic-evaluator** axis (reasoning + plan
  coherence, distinct from code quality).
- **Kanban board** projects task + event state: `sigma board --topic <t>`
  (`--watch` for live). **`sigma weave`** weaves the stage artifacts into one
  self-contained `chain.html` + a machine `chain.json`. Bundled skills live in
  `skills/vendor/`.

## Playground

New here? [`docs/PLAYGROUND.md`](docs/PLAYGROUND.md) is a hands-on tour of every
command and feature with copy-paste examples and expected output.

## License

MIT © Navid Ghayazi
