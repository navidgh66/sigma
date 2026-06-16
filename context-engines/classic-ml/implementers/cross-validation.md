---
domain: classic-ml
description: KFold, stratified, grouped, time-series, and nested CV — choosing the right splitter and avoiding leakage.
---

# Cross-Validation (classic ML)

## Pick the splitter by data structure
| Data property | Splitter |
|---------------|----------|
| i.i.d. classification | `StratifiedKFold` (preserves class balance) |
| i.i.d. regression | `KFold(shuffle=True, random_state=…)` |
| Repeated entities (user/patient/store) | `GroupKFold` / `StratifiedGroupKFold` |
| Time-ordered | `TimeSeriesSplit` (expanding window) |
| Model selection AND honest score | Nested CV |

## Standard usage
```python
from sklearn.model_selection import StratifiedKFold, cross_val_score
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
# pass the WHOLE pipeline so transforms refit per fold (no leakage)
scores = cross_val_score(pipeline, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
print(scores.mean(), scores.std())
```

## Grouped CV — when rows aren't independent
If the same user appears in train and test, you leak identity. Use groups:
```python
from sklearn.model_selection import StratifiedGroupKFold
cv = StratifiedGroupKFold(n_splits=5)
cross_val_score(pipeline, X, y, cv=cv, groups=df["user_id"], scoring="roc_auc")
```

## Time series — never shuffle
```python
from sklearn.model_selection import TimeSeriesSplit
cv = TimeSeriesSplit(n_splits=5, gap=24)  # gap avoids leakage from adjacent points
# fold k trains on [0..t], tests on (t..t+h]; always train-past / test-future
```
- Add a `gap` when features use lookback windows so train/test windows don't overlap.
- For deployment realism, optionally use a fixed test horizon, not expanding.

## Nested CV (unbiased estimate when you also tune)
```python
inner = StratifiedKFold(5, shuffle=True, random_state=1)
outer = StratifiedKFold(5, shuffle=True, random_state=2)
search = GridSearchCV(pipeline, param_grid, cv=inner, scoring="roc_auc")
nested_scores = cross_val_score(search, X, y, cv=outer)   # search refit inside each outer fold
```
The outer loop estimates generalization; the inner loop selects hyperparameters. Reporting the
inner best score as your performance is optimistic bias — that's what nesting fixes.

## Leakage traps in CV
- Scaling/encoding/imputing/target-encoding BEFORE `cross_val_score` -> leaks. Keep in pipeline.
- Feature selection on full data, then CV -> leaks. Selection must be inside the pipeline.
- Oversampling (SMOTE) before split -> leaks. Use `imblearn.pipeline.Pipeline`.
- Tuning on test set -> leaks. Test set is touched once, at the end.

## Pitfalls
- Default `KFold` does NOT shuffle — ordered data gives garbage folds. Set `shuffle=True`.
- `cross_val_score` silently ignores `groups` if you pass the wrong CV object.
- Tiny folds + rare classes: stratify or use `StratifiedKFold`.

## Checklist
- [ ] Splitter matches dependence structure (group/time)
- [ ] Whole pipeline (not just model) passed to CV
- [ ] No tuning on the held-out test set
- [ ] Report mean ± std, not a single fold
