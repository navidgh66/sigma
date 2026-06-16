---
domain: classic-ml
description: Encoding, scaling, leakage-safe feature engineering with sklearn ColumnTransformer + Pipeline.
---

# Feature Engineering (classic ML)

## The golden rule: fit on train only
Every stateful transform (scaler stats, encoder categories, imputer means, target stats)
must be learned on training folds and *applied* to validation/test. The only safe way to
guarantee this is to put transforms inside a `Pipeline` and let CV refit them per fold.

## ColumnTransformer + Pipeline (the standard skeleton)
```python
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer

num = ["age", "income", "tenure"]
cat = ["country", "plan"]

num_pipe = Pipeline([
    ("impute", SimpleImputer(strategy="median")),
    ("scale", StandardScaler()),
])
cat_pipe = Pipeline([
    ("impute", SimpleImputer(strategy="most_frequent")),
    # handle_unknown="ignore" -> unseen categories at predict time -> all-zeros row, no crash
    ("ohe", OneHotEncoder(handle_unknown="ignore", min_frequency=10)),
])

pre = ColumnTransformer(
    [("num", num_pipe, num), ("cat", cat_pipe, cat)],
    remainder="drop",            # be explicit; never silently pass columns through
    verbose_feature_names_out=False,
)
model = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=1000))])
model.fit(X_train, y_train)      # everything fit on train only
```

## Encoding choices
- **Low-cardinality nominal** -> OneHotEncoder. Set `min_frequency`/`max_categories` to cap blowup.
- **High-cardinality** (zip, user_id, SKU) -> target/mean encoding, but ONLY with cross-fold
  encoding (`category_encoders.TargetEncoder` or sklearn `TargetEncoder`, which does internal CV).
- **Ordinal with real order** -> `OrdinalEncoder(categories=[...])` with explicit order; do not let it infer.
- **Tree models** tolerate ordinal-encoded nominals and need no scaling; linear/SVM/NN do not.

## Scaling
- StandardScaler for roughly-Gaussian features; RobustScaler when heavy outliers (uses median/IQR).
- Never scale before train/test split outside a pipeline.
- Trees, RF, GBMs: scaling is a no-op — skip it.

## Leakage traps (most common production bugs)
- `fit_transform` on the full dataset, then split. WRONG — test stats leak into train.
- Target encoding / WOE without out-of-fold computation -> massive optimistic bias.
- Features derived from the future (e.g. `account_closed_date` predicting churn).
- Aggregations (`group mean`) computed over the whole dataset incl. test rows.
- Imputing with global mean computed before the split.

## Pitfalls
- OneHotEncoder without `handle_unknown="ignore"` crashes on unseen categories in prod.
- `SimpleImputer` silently drops dtype info; reattach feature names with `get_feature_names_out()`.
- Don't mix `set_output(transform="pandas")` expectations with estimators that emit sparse arrays.

## Checklist
- [ ] All stateful transforms inside a Pipeline
- [ ] CV refits the whole pipeline per fold
- [ ] No global aggregation/imputation before split
- [ ] Unknown-category handling set for prod inference
