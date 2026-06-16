---
domain: mlops
description: Production model monitoring — data drift, concept drift, performance decay, and alerting.
---

# Model Monitoring

## What decays and why
- **Data drift**: input distribution shifts (`P(X)` changes). Model sees inputs unlike training.
- **Concept drift**: relationship shifts (`P(y|X)` changes). Same inputs, different correct answer.
- **Performance decay**: the metric that matters drops. The thing you ultimately alert on.
- Labels often arrive late, so monitor input drift + proxy signals as early warnings.

## Three layers of monitoring
```python
# 1) Operational: latency, throughput, error rate, null rate per feature (catch pipeline breaks)
# 2) Data quality: schema match, range/null violations, unexpected categories
# 3) Drift + performance: distribution shift now vs training baseline; metric vs label
```

## Data drift detection
```python
from scipy.stats import ks_2samp
# numeric feature: KS test reference (training) vs production window
stat, p = ks_2samp(ref[col], prod_window[col])
drifted = p < 0.01
# categorical: PSI (Population Stability Index)
def psi(ref, cur, bins=10):
    import numpy as np
    r = np.histogram(ref, bins=bins)[0] / len(ref) + 1e-6
    c = np.histogram(cur, bins=bins)[0] / len(cur) + 1e-6
    return np.sum((c - r) * np.log(c / r))
# PSI <0.1 stable, 0.1-0.25 moderate shift, >0.25 significant -> investigate
```
Tools: Evidently, NannyML (estimates performance without labels via DLE/CBPE), whylogs.

## Performance monitoring
```python
# When labels land, compute rolling metric vs training baseline:
rolling_auc = roc_auc_score(y_true_window, preds_window)
alert = rolling_auc < baseline_auc - DEGRADATION_THRESHOLD   # e.g. 0.03 absolute
```
Monitor on key **slices**, not just overall — aggregate can hide a broken subgroup.

## Alerting (avoid fatigue)
- Tie thresholds to business impact, not p-values alone (a drifted feature the model barely uses
  may not matter).
- Alert on sustained shift, not single-window noise (require N consecutive windows).
- Severity tiers: warn (investigate) vs page (retrain/rollback). Route to an owner.
- Every alert needs a runbook: what to check, who decides, rollback vs retrain.

## Pitfalls
- Monitoring only accuracy with delayed labels -> you find out weeks late. Watch input drift now.
- Drift alarms on features the model ignores -> alert fatigue. Weight by feature importance.
- Overall metric only -> hidden subgroup failures.
- No training baseline stored -> nothing to compare against.
- Logging predictions without inputs -> can't diagnose drift root cause. Log both (PII-safe).

## Checklist
- [ ] Operational + data-quality + drift/performance layers covered
- [ ] Training baseline distributions + metrics stored for comparison
- [ ] Drift tests (KS/PSI) on important features; sliced performance
- [ ] Alerts tiered, sustained-shift-based, with runbooks and owners
- [ ] Inputs + predictions logged (PII-safe) for diagnosis
