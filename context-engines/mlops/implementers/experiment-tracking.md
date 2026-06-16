---
domain: mlops
description: Tracking experiments with MLflow — params, metrics, artifacts, and reproducible runs.
---

# Experiment Tracking (MLflow)

## Why
If you can't reproduce the run that produced a model, you can't debug, compare, or trust it.
Track everything needed to recreate a result: code version, data version, params, metrics, env.

## Minimal run
```python
import mlflow
mlflow.set_experiment("churn-v2")
with mlflow.start_run(run_name="lgbm-baseline") as run:
    mlflow.log_params({"lr": 0.03, "num_leaves": 63, "n_estimators": 2000})
    mlflow.set_tags({"git_sha": git_sha(), "data_version": "2024-03-01", "author": "ng"})

    model.fit(X_tr, y_tr)
    preds = model.predict_proba(X_val)[:, 1]
    mlflow.log_metrics({"val_auc": roc_auc_score(y_val, preds),
                        "val_logloss": log_loss(y_val, preds)})

    mlflow.log_artifact("confusion_matrix.png")
    # flavored logging captures signature + input example + env for reproducible serving:
    mlflow.sklearn.log_model(model, name="model",
                             signature=infer_signature(X_val, preds),
                             input_example=X_val.iloc[:5])
```

## What to log (and why)
- **Params**: every hyperparameter + preprocessing config. Comparisons are meaningless otherwise.
- **Metrics**: train AND val (and test once); log per-step for curves with `step=`.
- **Tags**: git SHA, data version/hash, dataset row count, environment — the reproducibility trio.
- **Artifacts**: plots, feature importances, the serialized model, requirements/conda env.
- **Model signature + input example**: enables schema validation and clean serving.

## Autologging (fast start)
```python
mlflow.sklearn.autolog()      # or mlflow.lightgbm / pytorch / xgboost
# Logs params, metrics, model automatically. Augment with manual log_metric for custom metrics.
```

## Comparing & promoting
```python
runs = mlflow.search_runs(experiment_names=["churn-v2"],
                          order_by=["metrics.val_auc DESC"])
best = runs.iloc[0]["run_id"]
# Promote the best run's model into the registry (see model-registry.md)
```

## Pitfalls
- Logging params but not data version -> "best" run on a different dataset, not comparable.
- Metrics without code/env capture -> not reproducible.
- Logging only final metric, no curves -> can't diagnose over/underfitting.
- Comparing runs across changed preprocessing without tracking it -> apples vs oranges.
- Secrets/PII in params or artifacts -> leak in tracking UI.
- One giant run for everything -> use nested runs (`nested=True`) for CV folds / sweeps.

## Checklist
- [ ] Params + preprocessing config logged
- [ ] git SHA + data version + env captured as tags/artifacts
- [ ] Train/val/test metrics logged (curves where useful)
- [ ] Model logged with signature + input example
- [ ] No secrets/PII in logged data
