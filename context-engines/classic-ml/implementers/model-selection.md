---
domain: classic-ml
description: Choosing linear, tree, ensemble, and boosting models — when each wins and sane defaults.
---

# Model Selection (classic ML)

## Decision shortcut
| Situation | Start with |
|-----------|-----------|
| Tabular, mixed types, want strong baseline | Gradient boosting (LightGBM/XGBoost) |
| Need interpretability / coefficients | Logistic / Linear / ElasticNet |
| Wide, sparse (text TF-IDF, one-hot) | Linear (LogReg, LinearSVC) |
| Small n, nonlinear, low dims | RBF SVM, RandomForest |
| Need calibrated probabilities | LogReg, or wrap in CalibratedClassifierCV |
| Many noisy features, want robustness | RandomForest / ExtraTrees |

**Always fit a dumb baseline first** (`DummyClassifier`, mean predictor, or plain LogReg).
A model that can't beat it is broken or the signal isn't there.

## Linear
```python
from sklearn.linear_model import LogisticRegression, ElasticNet
# class_weight="balanced" for imbalance; saga solver for L1/elasticnet on big data
LogisticRegression(penalty="l2", C=1.0, class_weight="balanced", max_iter=2000)
```
- Needs scaled features. Fast, interpretable, great on high-dim sparse.
- L1 (lasso) for sparsity/feature selection; ElasticNet when features correlate.

## Trees & forests
- Single `DecisionTree`: interpretable but high variance — rarely use alone.
- `RandomForest`: bagged trees, strong default, handles nonlinearity, no scaling.
  Tune `n_estimators` (more = better but slower, diminishing), `max_features`, `min_samples_leaf`.
- `ExtraTrees`: more randomized splits, faster, sometimes better.

## Boosting (usually the winner on tabular)
```python
import lightgbm as lgb
clf = lgb.LGBMClassifier(
    n_estimators=2000, learning_rate=0.03, num_leaves=63,
    subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
)
clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(0)])
```
- LightGBM: fastest, handles categoricals natively (`categorical_feature=`), best big-data default.
- XGBoost: similar power, robust, great regularization knobs.
- CatBoost: best out-of-box on high-cardinality categoricals, less tuning.
- **Always use early stopping with a validation set** — set high `n_estimators` and let it stop.

## Pitfalls
- Boosting overfits with high LR + no early stopping. Low LR + many trees + early stop.
- RandomForest probabilities are poorly calibrated — calibrate if you need real probabilities.
- SVM (RBF) scales O(n^2)+; don't use beyond ~50k rows.
- Don't grid-search 6 model families blindly — pick 2-3 by data shape, then tune.

## Checklist
- [ ] Baseline beaten by a clear margin
- [ ] Model family matches data shape (sparse->linear, tabular->boosting)
- [ ] Early stopping on boosting
- [ ] Calibration considered if probabilities are used downstream
