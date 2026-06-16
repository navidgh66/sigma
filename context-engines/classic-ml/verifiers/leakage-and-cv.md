---
domain: classic-ml
description: PASS/WARN/FAIL verifier for data leakage and cross-validation correctness.
---

# Verifier: Leakage & CV Correctness

Run these checks against any modeling code/notebook before trusting its scores.

## FAIL (block — results are invalid)
- **F1 fit-before-split**: any `fit`/`fit_transform`/scaler/encoder/imputer called on the full
  dataset before `train_test_split`. Grep for `.fit_transform(X)` outside a Pipeline.
- **F2 test in tuning**: `GridSearchCV`/`RandomizedSearchCV`/Optuna objective references X_test/y_test.
- **F3 resampling before split**: `SMOTE`/`RandomOverSampler` applied before CV split (must be in
  `imblearn.pipeline.Pipeline`).
- **F4 target encoding without OOF**: mean/target/WOE encoding computed on full data or without
  cross-fold scheme.
- **F5 future features**: a feature uses information unavailable at prediction time
  (post-outcome timestamps, downstream-of-label aggregates).
- **F6 grouped data, ungrouped CV**: repeated entities (user/store/patient) split with plain
  KFold so the same entity lands in train and test.
- **F7 time series shuffled**: temporal data uses `KFold(shuffle=True)` or random split.

## WARN (likely problem — justify or fix)
- **W1**: default `KFold` without `shuffle=True` on non-temporal data (ordered input -> bad folds).
- **W2**: feature selection / dimensionality reduction outside the pipeline.
- **W3**: single train/test split reported with no CV (no variance estimate).
- **W4**: tuning best CV score reported as final performance (no held-out test / nested CV).
- **W5**: scoring metric mismatched to objective (accuracy on imbalanced data).
- **W6**: no fixed `random_state` on splitters/search (non-reproducible).
- **W7**: very high CV score (>0.99 AUC) — smell of leakage; investigate top features.

## PASS (good signs)
- All transforms inside a `Pipeline`/`ColumnTransformer`; CV refits per fold.
- Splitter matches structure: Stratified for class balance, Group for entities, TimeSeriesSplit for time.
- Test set referenced exactly once, after tuning.
- Metrics reported as mean ± std across folds.
- Seeds set everywhere; results reproducible.

## Quick audit snippet
```python
from sklearn.pipeline import Pipeline
assert isinstance(model, Pipeline), "F1 risk: transforms must live in a Pipeline"
# leakage smoke test: shuffle labels -> score must collapse to chance
import numpy as np
y_perm = np.random.permutation(y_train)
s = cross_val_score(model, X_train, y_perm, cv=cv, scoring="roc_auc").mean()
assert s < 0.55, f"Leakage suspected: AUC {s:.3f} on permuted labels"
```

## Verdict format
```
LEAKAGE & CV: FAIL
- F1 (line 42): StandardScaler().fit_transform(X) before split
- F6: user_id repeats across folds, plain KFold used
Fix F1, F6 before any reported metric is trusted.
```
