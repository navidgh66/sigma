---
domain: data-analysis
description: Choosing and running t-test, chi-square, ANOVA in scipy/statsmodels — assumptions and effect sizes.
---

# Statistical Testing

## Test selection
| Question | Test |
|----------|------|
| Mean of 2 independent groups (numeric) | Independent t-test (Welch) / Mann-Whitney if non-normal |
| Mean before/after, same units | Paired t-test / Wilcoxon signed-rank |
| Mean of 3+ groups | One-way ANOVA / Kruskal-Wallis |
| Association of 2 categoricals | Chi-square / Fisher exact (small cells) |
| Linear association of 2 numerics | Pearson / Spearman (monotonic) |

## t-test (use Welch by default)
```python
from scipy import stats
# equal_var=False = Welch: does NOT assume equal variances — safer default
t, p = stats.ttest_ind(group_a, group_b, equal_var=False)
# Effect size (Cohen's d) — ALWAYS report alongside p
import numpy as np
d = (group_a.mean() - group_b.mean()) / np.sqrt((group_a.var(ddof=1)+group_b.var(ddof=1))/2)
```
Assumptions: independence, approx-normal (or large n via CLT), reasonable variance. Check
normality with a QQ-plot, not just Shapiro (which over-rejects on big n).

## Chi-square / Fisher
```python
import pandas as pd
ct = pd.crosstab(df.segment, df.converted)
chi2, p, dof, expected = stats.chi2_contingency(ct)
# If any expected cell < 5 -> use Fisher exact (2x2):
odds, p = stats.fisher_exact(ct)
# Effect size: Cramér's V
```
Assumption: expected cell counts >= 5; independent observations.

## ANOVA
```python
f, p = stats.f_oneway(g1, g2, g3)         # one-way
# Assumptions: normal residuals, homogeneity of variance (Levene), independence
stats.levene(g1, g2, g3)                  # p<0.05 -> variances differ -> use Welch ANOVA
# Significant ANOVA -> post-hoc Tukey HSD to find WHICH groups differ:
from statsmodels.stats.multicomp import pairwise_tukeyhsd
pairwise_tukeyhsd(df.value, df.group)
```
Don't run pairwise t-tests after ANOVA without correction — that inflates Type I error.

## Non-parametric fallbacks
- `stats.mannwhitneyu` (vs t-test), `stats.wilcoxon` (paired), `stats.kruskal` (vs ANOVA).
- Use when normality clearly fails AND n is small, or data is ordinal.

## Pitfalls
- p < 0.05 != important. Always report effect size + confidence interval.
- Large n makes trivial differences "significant" — judge practical effect.
- Multiple tests inflate false positives — correct (Bonferroni/BH); see stat-soundness verifier.
- Paired data analyzed as independent -> wrong variance, wrong p.
- One-sided tests chosen after seeing the data = p-hacking.
- Normality tests over-reject on large samples; trust QQ-plots and CLT.

## Checklist
- [ ] Test matches data type + design (paired/independent, 2 vs 3+ groups)
- [ ] Assumptions checked (normality, equal variance, expected counts)
- [ ] Effect size + CI reported, not just p
- [ ] Hypothesis + alpha fixed before looking at data
- [ ] Multiple-comparison correction applied where relevant
