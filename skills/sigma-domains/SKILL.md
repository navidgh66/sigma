---
name: sigma-domains
description: >
  Auto-surface the right sigma domain context-engine when implementing or
  verifying a data-science / AI-engineering task. Routes to hand-authored
  implementer guidance, verifier checks, and a logic-evaluator for the matching
  domain. Use when a task touches: classical ML (scikit-learn, feature
  engineering, cross-validation, model selection), deep learning (PyTorch /
  TensorFlow, training loops, architectures, distributed training), NLP
  (tokenization, transformers, classification, NER, semantic search,
  summarization), reinforcement learning (policy gradient, actor-critic,
  value-based, reward shaping, RLHF, environments), data analysis (EDA, A/B
  testing, statistical testing), data engineering (Airflow DAGs, dbt models,
  Spark jobs, pipelines), AI agent engineering (agent harness design, tool
  definitions, orchestration, evals), MLOps (experiment tracking, model registry,
  monitoring, production readiness), or LLM engineering (prompt engineering, RAG,
  fine-tuning, LLM evals). Trigger when about to write or review code in any of
  these areas, or when a sigma task is annotated with a domain.
origin: sigma
---

# sigma-domains

Load the **domain context-engine** that fits the task before implementing or
verifying. Each domain ships three kinds of guidance, kept as the single source
of truth under `context-engines/<domain>/`:

- `implementers/*.md` — how to build it correctly (the MAKER guidance).
- `verifiers/*.md` (minus the logic file) — PASS/WARN/FAIL checks (the CHECKER).
- `verifiers/logic-evaluator.md` — reasoning / plan-coherence grading (a third,
  distinct axis from code-quality verification).

This skill **indexes** those files — it does not copy them. Always read the
actual file for current guidance.

## Pick the domain

| Domain | Use when the task is about |
|--------|----------------------------|
| `classic-ml` | scikit-learn, feature engineering, cross-validation, hyperparameter tuning, model selection |
| `deep-learning` | PyTorch / TensorFlow models, training loops, architectures (CNN/RNN/Transformer), distributed training, determinism/devices |
| `nlp` | tokenization, transformer fine-tuning, classification, NER / sequence labeling, semantic search, generation / summarization |
| `rl` | policy gradient, actor-critic, value-based methods, reward shaping, RLHF, environment design, reward hacking |
| `data-analysis` | EDA, A/B testing, statistical testing / soundness |
| `data-engineering` | Airflow DAGs, dbt models, Spark jobs, pipeline soundness |
| `ai-agent-engineering` | agent harness design, tool definitions, orchestration, agent evals / soundness |
| `mlops` | experiment tracking, model registry, monitoring, production readiness |
| `llm-engineering` | prompt engineering, RAG, fine-tuning, LLM evals / soundness |

If a sigma task line is annotated `(domain)` (e.g. `- [ ] T1 (nlp): ...`), use
that domain directly.

## Workflow

1. **Match** the task to a domain from the table above.
2. **Implementing?** Read `context-engines/<domain>/implementers/` and open the
   file(s) matching the sub-task (filenames are specific, e.g.
   `nlp/implementers/tokenization.md`). Follow that guidance; make the smallest
   correct change.
3. **Verifying?** Read `context-engines/<domain>/verifiers/` (the non-logic
   files) and apply the PASS/WARN/FAIL checks. The implementer and verifier must
   be different agents (maker ≠ checker).
4. **Logic check?** Read `context-engines/<domain>/verifiers/logic-evaluator.md`
   and grade plan↔implementation coherence and reasoning soundness — NOT style.
   This is a third distinct agent from both maker and checker.

## Rules

- `context-engines/` is the source of truth — read the file, don't rely on this
  table for technical detail.
- Keep maker / checker / logic-evaluator as distinct roles (sigma enforces the
  separation in `cli/loop.py`).
- Load only the domain(s) a task actually needs (lean context).
