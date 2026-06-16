# Context Engine: mlops

Domain knowledge for **MLOps & production ML**.

## Scope
- Experiment tracking (MLflow, Weights & Biases) — params, metrics, artifacts
- Model registry & versioning (staging→prod promotion, model cards)
- CD4ML (versioned code+data+model, reproducible pipelines, automated retraining)
- Serving (batch, real-time endpoints, feature/serving skew avoidance)
- Monitoring (data drift, concept drift, performance degradation, alerts)
- Feature stores (Tecton, Feast) — train/serve consistency
- CACE principle (Changing Anything Changes Everything) — coupling discipline
- Safety (guardrails, canary deploys, automated rollback, shadow mode)

## Implementers
`implementers/` — experiment-tracking, model-registry, cd4ml-pipelines, serving,
monitoring, feature-stores.

## Verifiers
`verifiers/` — train/serve skew, drift detection wired, rollback thresholds set,
reproducibility, model-card completeness.

> 🚧 Seed file.
