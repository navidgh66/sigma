---
domain: mlops
description: Model versioning and stage promotion (staging->prod) with MLflow registry and model cards.
---

# Model Registry

## Purpose
The registry is the source of truth for "which model is in production". It versions models,
tracks stage (staging/prod/archived), and links each version back to the run that made it.

## Register & version
```python
import mlflow
result = mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",   # ties version to its experiment run (lineage)
    name="churn-classifier",
)
# Each register_model creates a new immutable version: v1, v2, ...
```

## Promotion via aliases (modern MLflow) or stages
```python
client = mlflow.MlflowClient()
# Aliases (preferred over deprecated stages):
client.set_registered_model_alias("churn-classifier", "champion", version=result.version)
client.set_registered_model_alias("churn-classifier", "challenger", version=other_version)
# Serving code loads by alias, not a pinned version:
model = mlflow.pyfunc.load_model("models:/churn-classifier@champion")
```
Promotion flow: register -> validate in staging (offline + shadow) -> promote to champion ->
keep previous champion addressable for instant rollback.

## Promotion gates (don't promote blindly)
1. Beats current champion on the offline eval set by a meaningful margin.
2. Passes the production-readiness verifier (no train/serve skew, schema matches).
3. Shadow/canary in prod shows acceptable live metrics.
4. Model card reviewed and attached.

## Model card (attach as artifact / description)
Document, at minimum:
- **Intended use** and out-of-scope uses.
- **Training data**: source, version, date range, known biases.
- **Metrics**: offline performance overall + on key slices (fairness/subgroups).
- **Limitations & failure modes**; monitoring plan; owner; retrain cadence.
```python
client.update_model_version(name="churn-classifier", version=v,
    description="Trained on 2024-03 snapshot. AUC 0.87. Underperforms on <30d-tenure segment.")
```

## Rollback
```python
# Instant rollback: repoint the alias to the prior version. No redeploy of artifacts needed.
client.set_registered_model_alias("churn-classifier", "champion", version=previous_version)
```

## Pitfalls
- Serving a pinned version number -> rollback requires a code change/redeploy. Use aliases.
- No lineage from version back to run -> can't reproduce or audit a prod model.
- Promoting on offline metrics alone -> live skew burns you. Gate on shadow/canary.
- Deleting old versions -> no rollback target. Archive, don't delete.
- No model card -> nobody knows the model's limits or owner when it misbehaves.

## Checklist
- [ ] Every prod model registered with run lineage
- [ ] Serving loads by alias (champion), not pinned version
- [ ] Promotion gated on offline + shadow/canary + readiness check
- [ ] Model card attached (use, data, metrics, limits, owner)
- [ ] Previous champion retained for instant rollback
