---
domain: classic-ml
description: Grid, random, and Optuna hyperparameter search with leakage-safe pipelines and early stopping.
---

# Hyperparameter Tuning (classic ML)

## Method by budget
| Budget | Use |
|--------|-----|
| Few params, small space | `GridSearchCV` |
| Many params, limited compute | `RandomizedSearchCV` (often beats grid) |
| Large space, want efficiency | Optuna (TPE) with pruning |
| Boosting `n_estimators` | Don't tune — use early stopping |

## Random search (strong default)
```python
from sklearn.model_selection import RandomizedSearchCV
from scipy.stats import loguniform, randint
param_dist = {
    "clf__C": loguniform(1e-3, 1e3),
    "clf__l1_ratio": [0, .2, .5, .8, 1],
}
search = RandomizedSearchCV(
    pipeline, param_dist, n_iter=60, cv=StratifiedKFold(5, shuffle=True, random_state=0),
    scoring="roc_auc", n_jobs=-1, random_state=0, refit=True,
)
search.fit(X_train, y_train)        # tune on TRAIN, never test
print(search.best_params_, search.best_score_)
```
Note the `clf__` prefix — params address steps inside the pipeline so transforms refit per fold.

## Optuna (efficient, prunes bad trials early)
```python
import optuna, lightgbm as lgb
from sklearn.model_selection import cross_val_score, StratifiedKFold

def objective(trial):
    params = {
        "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
        "num_leaves":    trial.suggest_int("num_leaves", 15, 255),
        "subsample":     trial.suggest_float("subsample", 0.5, 1.0),
        "reg_lambda":    trial.suggest_float("reg_lambda", 1e-3, 10, log=True),
        "n_estimators":  2000,
    }
    model = lgb.LGBMClassifier(**params)
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    # eval via CV; for speed use early stopping inside a manual fold loop
    return cross_val_score(model, X_train, y_train, cv=cv, scoring="roc_auc").mean()

study = optuna.create_study(direction="maximize",
                            sampler=optuna.samplers.TPESampler(seed=0),
                            pruner=optuna.pruners.MedianPruner())
study.optimize(objective, n_trials=100, timeout=3600)
```
- Use `log=True` for scale params (`C`, `learning_rate`, `reg_lambda`).
- Add `optuna.integration.LightGBMPruningCallback` to kill weak trials mid-training.
- Seed sampler for reproducibility; persist study with a `storage=` SQLite URL.

## Pitfalls
- Tuning on the test set — the cardinal sin. Test set is opened once.
- Reporting `best_score_` as final performance is optimistic; confirm on a held-out test set
  or use nested CV.
- Linear scales (e.g. C in [1,10,100]) waste trials — use log-uniform.
- Over-tuning to CV noise: if std across folds > gain from tuning, stop.
- Forgetting the `step__param` prefix so the search silently tunes nothing.

## Checklist
- [ ] Search runs on train only; test untouched until final eval
- [ ] Log-scale priors for multiplicative params
- [ ] Boosting tree count handled by early stopping, not search
- [ ] Pipeline-prefixed param names verified
- [ ] Reproducible (seeded sampler / random_state)
