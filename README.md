# σ sigma

> **Personal AI workflow toolkit for data science & AI engineering.**
> Clone once. Works everywhere. Research-first, spec-driven, loop-engineered.

`sigma` is a portable, composable workflow system that wraps Claude Code with a
disciplined pipeline built for data scientists and AI engineers — from classic ML
to deep learning, NLP, reinforcement learning, data engineering, MLOps, LLM
engineering, and AI-agent-harness engineering.

It is inspired by [an internal tool](https://github.com/internal/an internal tool),
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

```bash
# one command, global
curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh
export PATH="$PATH:$HOME/.local/bin"
sigma --help
```

## Use

```bash
sigma init          # per-project: pick domains, write sigma.config.yml
sigma               # launch Claude Code with sigma context loaded
```

---

## Status

🚧 **Early scaffold.** See [`docs/`](docs/) for the design doc and roadmap.

## License

MIT © Navid Ghayazi
