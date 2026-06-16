---
domain: data-analysis
description: PASS/WARN/FAIL verifier for statistical soundness — assumptions, multiple comparisons, p-hacking.
---

# Verifier: Statistical Soundness

## FAIL (block — conclusion not defensible)
- **F1 wrong test**: paired data tested as independent, 3+ groups via repeated t-tests,
  categorical association via t-test, etc.
- **F2 uncorrected multiplicity**: many tests/metrics/segments, no Bonferroni/BH/FDR control,
  yet a "significant" result is claimed.
- **F3 peeking + early stop**: test stopped at first p<0.05 without a sequential method
  (alpha-spending / always-valid).
- **F4 HARKing / metric switching**: hypothesis or primary metric chosen after seeing data;
  one-sided test selected post-hoc.
- **F5 SRM ignored**: A/B arm counts deviate from design and no SRM check was run.
- **F6 p-only conclusion on huge n**: significance claimed with no effect size, where n is large
  enough to make trivial effects significant.

## WARN (justify or fix)
- **W1**: normality assumed for small-n t-test/ANOVA without a QQ-plot or non-parametric fallback.
- **W2**: equal-variance t-test (`equal_var=True`) without a variance check — prefer Welch.
- **W3**: chi-square with expected cell counts < 5 (should use Fisher exact).
- **W4**: heavy-tailed metric (revenue) analyzed with mean-based t-test instead of bootstrap/trimmed.
- **W5**: no confidence interval reported alongside the point estimate.
- **W6**: underpowered design (no a-priori power/sample-size calc).
- **W7**: outliers silently removed to push p under 0.05.

## PASS
- Test matches design (paired/independent, 2 vs 3+, numeric vs categorical).
- Assumptions checked (normality via QQ, variance via Levene, expected counts).
- Alpha, power, sample size, primary metric, stopping rule fixed before data.
- Effect size + CI reported with the p-value.
- Multiplicity corrected; SRM verified for experiments.
- Sequential method used if the test was monitored.

## Quick checks
```python
# Multiplicity correction
from statsmodels.stats.multitest import multipletests
reject, p_adj, *_ = multipletests(pvals, alpha=0.05, method="fdr_bh")

# SRM check (expected 50/50)
from scipy.stats import chisquare
chi2, p = chisquare([n_a, n_b], f_exp=[(n_a+n_b)/2]*2)
assert p > 0.001, "SRM detected — experiment assignment is broken"
```

## Verdict format
```
STAT SOUNDNESS: FAIL
- F2: 14 segment tests, no FDR correction, 'segment X significant' claimed
- F5: arms 53/47 with no SRM check
Apply BH correction; run SRM before reporting.
```
