---
domain: data-analysis
description: Fast, leakage-aware EDA with pandas/polars — profiling, missingness, outliers, distributions.
---

# Exploratory Data Analysis

## First five minutes
```python
import pandas as pd
df.shape, df.dtypes
df.head(), df.sample(5)
df.describe(include="all").T          # numeric + categorical summary
df.isna().mean().sort_values(ascending=False)   # missingness fraction per column
df.nunique().sort_values()            # spot IDs, constants, high-cardinality
df.duplicated().sum()
```
Do EDA on the **training split only** if you later model — exploring test informs choices = leakage.

## Polars for large data
```python
import polars as pl
df = pl.scan_parquet("data/*.parquet")     # lazy; no full load
df.select(pl.all().null_count()).collect()
df.group_by("country").agg(pl.col("revenue").mean()).collect()
# Lazy scans + predicate pushdown beat pandas on multi-GB data.
```

## Missingness
```python
miss = df.isna().mean()
# Classify: MCAR/MAR/MNAR matters for imputation choice.
# Visualize co-missingness — columns missing together hint at a join/source issue.
import missingno as msno; msno.matrix(df); msno.heatmap(df)
```
- High-missing columns (>60%): consider dropping or a missingness-indicator feature.
- Don't impute during EDA exploration; decide strategy, apply inside the modeling pipeline.

## Outliers
```python
q1, q3 = df["x"].quantile([.25, .75]); iqr = q3 - q1
mask = (df["x"] < q1 - 1.5*iqr) | (df["x"] > q3 + 1.5*iqr)
# Robust z-score (median/MAD) is better than mean/std for skewed data:
from scipy.stats import median_abs_deviation
z = 0.6745 * (df["x"] - df["x"].median()) / median_abs_deviation(df["x"])
```
Investigate, don't auto-delete: outliers are sometimes the signal (fraud, faults).

## Distributions & relationships
- Histograms + KDE per numeric; log-scale heavy-tailed (income, counts).
- `df.corr(numeric_only=True)` then heatmap; Spearman for monotonic non-linear.
- For target: plot feature vs target (boxplot per category, scatter + lowess).
- Check class balance early — drives metric and resampling decisions.

## Data quality smells
- Mixed types in a column (object dtype hiding numbers + strings).
- Sentinel values (`-999`, `9999`, `"N/A"`, empty string) masquerading as data.
- Timestamps as strings; parse and check ranges/timezones.
- Categorical typos / inconsistent casing (`"US"` vs `"us"` vs `"USA"`).
- Implausible values (negative age, future dates).

## Pitfalls
- `describe()` ignores object columns unless `include="all"`.
- `.corr()` silently drops non-numeric — verify the columns it used.
- Profiling tools (`ydata-profiling`) are great but choke on wide/huge frames — sample first.
- EDA on full dataset then modeling = subtle leakage of distribution knowledge.

## Checklist
- [ ] Shape, dtypes, missingness, cardinality, duplicates checked
- [ ] Sentinel/typo/timezone issues found and noted
- [ ] Class balance and target relationships inspected
- [ ] Heavy work done on train split, not test
