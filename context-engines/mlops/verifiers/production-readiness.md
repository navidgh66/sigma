---
domain: mlops
description: PASS/WARN/FAIL verifier for production readiness — train/serve skew, rollback, reproducibility.
---

# Verifier: Production Readiness

## FAIL (block deploy)
- **F1 train/serve skew**: feature computation differs between training and serving (different
  code paths, libraries, or aggregation windows). The #1 cause of "great offline, bad in prod".
- **F2 no rollback path**: prod model pinned by version with no alias/previous-champion to revert
  to; rollback requires a redeploy.
- **F3 not reproducible**: model artifact has no link to git SHA + data version + env; the run
  cannot be recreated.
- **F4 no input contract at serving**: serving accepts inputs without schema/range validation,
  so malformed/missing features silently produce garbage predictions.
- **F5 no monitoring**: model deployed with no drift/performance/operational monitoring or alerts.
- **F6 promotion on offline only**: promoted to prod with no shadow/canary validation against live traffic.

## WARN (justify or fix)
- **W1**: no defined rollback threshold (what live metric triggers revert?).
- **W2**: training/serving on different library versions (pin and pickle the env).
- **W3**: no sliced offline metrics (subgroup failures invisible).
- **W4**: model card missing (intended use, limits, owner, retrain cadence).
- **W5**: predictions logged without inputs -> can't diagnose drift.
- **W6**: no load/latency test for serving SLA.
- **W7**: no defined retrain cadence/trigger.

## PASS
- Identical feature code/transform path in train and serve (shared pipeline or feature store).
- Serving validates input against the model signature/schema; rejects/flags bad input.
- Model artifact linked to git SHA + data version + frozen env; reproducible.
- Promotion gated on offline + shadow/canary; alias-based champion with prior version retained.
- Monitoring (operational + data + drift + sliced performance) live with tiered alerts + runbooks.
- Rollback thresholds defined; revert is a single alias repoint.

## Quick checks
```python
# train/serve skew smoke: same input -> same features both paths
assert np.allclose(train_pipeline.transform(x), serving_featurizer(x)), "F1 skew"
# reproducibility
assert model.metadata.get("git_sha") and model.metadata.get("data_version"), "F3"
# input contract
schema_ok = signature.inputs.validate(request_df)   # reject on mismatch
```

## Verdict format
```
PRODUCTION READINESS: FAIL
- F1: serving recomputes 7d_avg with a different window than training
- F2: serving loads models:/m/3 (pinned) — no rollback alias
Unify feature code via shared pipeline; serve by @champion alias with prior retained.
```
