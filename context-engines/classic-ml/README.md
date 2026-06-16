# Context Engine: classic-ml

Domain knowledge for **classical machine learning** with scikit-learn and friends.

## Scope
- Feature engineering (encoding, scaling, selection, leakage avoidance)
- Model selection (linear models, trees, ensembles, SVM, kNN, gradient boosting)
- Cross-validation strategies (k-fold, stratified, time-series splits, nested CV)
- Hyperparameter tuning (grid, random, Bayesian/Optuna)
- Pipelines (`sklearn.pipeline`, `ColumnTransformer`, reproducible preprocessing)
- Evaluation (metrics by task, calibration, error analysis)
- Imbalanced data (resampling, class weights, threshold tuning)

## Implementers
See `implementers/` — one file per concern (feature-engineering, model-selection,
cross-validation, hyperparameter-tuning, pipelines).

## Verifiers
See `verifiers/` — checks for data leakage, reproducible seeds, correct CV usage,
metric appropriateness.

> 🚧 Seed file. Deepen with real patterns as the toolkit matures.
