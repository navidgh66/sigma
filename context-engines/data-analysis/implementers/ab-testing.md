---
domain: data-analysis
description: A/B test design and analysis — power, sample size, sequential testing, and p-hacking guards.
---

# A/B Testing

## Design BEFORE you collect data
1. Define one primary metric and the minimum detectable effect (MDE) that matters.
2. Fix alpha (0.05) and power (0.80) up front.
3. Compute required sample size; commit to it.
4. Pre-register: hypothesis, metric, segments, stopping rule.

## Sample size & power
```python
from statsmodels.stats.power import TTestIndPower, NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize
# Proportion metric (conversion): baseline 5%, want to detect +1pp
es = proportion_effectsize(0.05, 0.06)
n = NormalIndPower().solve_power(effect_size=es, alpha=0.05, power=0.80, alternative="two-sided")
print(f"{n:.0f} per arm")
# Continuous metric: effect_size = (mu1-mu0)/pooled_sd
```
Underpowered tests waste traffic and produce noise dressed as conclusions.

## Analysis (after reaching planned n)
```python
from statsmodels.stats.proportion import proportions_ztest
import numpy as np
counts = np.array([conv_a, conv_b]); nobs = np.array([n_a, n_b])
z, p = proportions_ztest(counts, nobs)
# Always report lift + CI, not just p:
from statsmodels.stats.proportion import confint_proportions_2indep
lift_ci = confint_proportions_2indep(conv_b, n_b, conv_a, n_a)
```
For revenue/AOV (heavy-tailed) use bootstrap CIs or trimmed means, not a raw t-test.

## Sequential testing (peeking safely)
Naively checking the test repeatedly and stopping at first p<0.05 inflates false positives badly.
Options:
- **Group sequential** (O'Brien-Fleming / Pocock alpha-spending) — pre-set looks, adjusted bounds.
- **Always-valid p-values** (mSPRT / confidence sequences, e.g. Optimizely/`confseq`) — valid at any peek.
- Otherwise: fix the horizon, analyze once.

## p-hacking guards
- No peeking-and-stopping without a sequential method.
- No metric switching after seeing results (the "we found a winning segment" trap).
- Correct for multiple metrics/segments (Bonferroni/BH).
- Decide direction (one vs two-sided) before data.
- Report all pre-registered metrics, not just the significant one.

## Validity checks
- **Sample Ratio Mismatch (SRM)**: assignment should match design (e.g. 50/50). Chi-square the
  arm counts; p<0.001 SRM means a broken pipeline — STOP, results invalid.
- **A/A test** to validate instrumentation before A/B.
- Novelty/primacy effects: run long enough to stabilize; check by-day trends.
- Spillover/interference between arms (network effects) breaks independence.

## Pitfalls
- Stopping early on a lucky peek.
- Ignoring SRM — the most common silent invalidator.
- Multiple comparisons across many metrics with no correction.
- Treating revenue with a t-test despite extreme skew.
- Confusing statistical significance with business significance.

## Checklist
- [ ] MDE, alpha, power, sample size fixed before launch
- [ ] Primary metric + stopping rule pre-registered
- [ ] SRM check passes
- [ ] Sequential method used if peeking
- [ ] Lift + CI + effect reported; corrections applied for multiplicity
