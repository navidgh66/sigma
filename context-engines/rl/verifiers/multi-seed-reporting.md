---
domain: rl-verify-multi-seed-reporting
description: Verify RL results are reported across multiple seeds with confidence intervals, not a single lucky run.
---

# Verifier: Multi-Seed Reporting

RL is high-variance. A single seed proves nothing — the same config can range from solved to failed. Reported results must aggregate over multiple seeds with uncertainty.

## Checks

1. **>= 5 seeds** (10 preferred) per configuration. 3 is a bare minimum and only for cheap envs.
2. **Distinct, fixed seeds** controlling env, action sampling, and network init — logged.
3. **Reported with dispersion**: mean ± std, or better, a confidence interval / IQM. Never a bare single number.
4. **Same eval protocol per seed**: fixed number of eval episodes, deterministic or sampled consistently.
5. **Comparisons are fair**: same seed set, same budget (steps/samples), same eval, across the methods being compared.
6. **Learning curves** show the spread (shaded region), not just final value.

## Aggregation snippet

```python
import numpy as np
from scipy import stats

def report(scores):                 # scores: final eval return per seed
    scores = np.asarray(scores, dtype=float)
    mean, sem = scores.mean(), stats.sem(scores)
    ci = stats.t.interval(0.95, len(scores) - 1, loc=mean, scale=sem)
    return {"n": len(scores), "mean": mean, "std": scores.std(ddof=1),
            "ci95": ci, "min": scores.min(), "max": scores.max()}
# Prefer IQM (interquartile mean) + stratified bootstrap CI for robustness
# (rliable library) — less sensitive to outlier seeds than mean.
```

## Better practice (rliable)

For papers/serious comparisons, report **IQM** with **stratified bootstrap CIs** and **probability of improvement** rather than mean±std — the mean is dominated by lucky/unlucky outlier seeds. Plot performance profiles.

## Verdict criteria

- **PASS**: >= 5 distinct logged seeds, results as mean±std or CI (ideally IQM+bootstrap CI), learning curves with spread, fair matched comparison.
- **WARN**: 3–4 seeds, or mean±std where IQM would be more honest given outliers, or curves shown but final table lacks CIs.
- **FAIL**: single seed reported as "the result", seeds not fixed/logged, no dispersion at all, or methods compared under different budgets/eval protocols.

## Common findings

- One seed cherry-picked; rerun with a different seed collapses the result.
- "Mean over 5 runs" with no std, hiding that 2 of 5 failed entirely.
- Bar chart with no error bars.
- Baseline run for fewer steps than the proposed method (unfair budget).
- Eval episode count differs between seeds, conflating variance sources.
