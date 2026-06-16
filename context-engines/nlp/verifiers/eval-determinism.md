---
domain: nlp-verify-eval-determinism
description: Verify seeds are set, evaluation is reproducible, and the chosen metric fits the task.
---

# Verifier: Evaluation Determinism & Metric Fit

Goal: a reported number must be reproducible and meaningful. This verifier checks that randomness is controlled, eval is deterministic, and the metric matches the problem.

## Seeding checks

All sources of randomness must be seeded before any data shuffling or model init:

```python
import random, numpy as np, torch, os

def set_all_seeds(seed=42):
    random.seed(seed); np.random.seed(seed)
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

# HF: TrainingArguments(seed=..., data_seed=...) and transformers.set_seed(seed)
```

Verify:
- Single global seed set and logged.
- `Trainer` got `seed` (and `data_seed` if shuffling differs).
- Data split uses a fixed `random_state`/`seed` and is stratified where relevant.
- For full determinism on GPU: `torch.use_deterministic_algorithms(True)` and `CUBLAS_WORKSPACE_CONFIG=:4096:8` (note: slower, some ops unsupported).

## Eval-must-be-deterministic checks

- **No sampling at eval.** Generation eval uses greedy/beam (`do_sample=False`), not `temperature`/`top_p`. Sampling → non-reproducible metrics.
- **`model.eval()`** is set: dropout off, batchnorm in eval mode.
- **No data leakage** between train/val/test; dedupe before split.
- Run eval twice, expect identical (or within float tolerance) results:

```python
m1 = trainer.evaluate(); m2 = trainer.evaluate()
assert abs(m1["eval_f1"] - m2["eval_f1"]) < 1e-6, "eval is non-deterministic"
```

## Metric appropriateness

- Imbalanced classification → macro-F1, not accuracy.
- NER → entity-level seqeval, not token accuracy.
- Generation/summarization → ROUGE + a semantic metric (BERTScore); ROUGE alone misses paraphrase.
- Retrieval → Recall@k / MRR / nDCG, not accuracy.
- Report the metric **with the split it was computed on** and the seed.

## Verdict criteria

- **PASS**: seeds set and logged, eval deterministic across reruns, `model.eval()` set, no sampling at eval, metric fits the task and reports variance where multiple seeds are used.
- **WARN**: deterministic but single-seed only (no variance estimate) on a noisy task, or GPU nondeterminism from unseeded CUDA ops with small impact.
- **FAIL**: unseeded run, sampling used for reported generation metrics, accuracy reported on imbalanced data, train/test leakage, or metrics differ between identical reruns.

## Common findings

- `set_seed` called after the dataset shuffle, so the split still varies.
- Eval generation left `do_sample=True` → ROUGE wobbles run to run.
- One lucky seed reported as "the" result with no CI (see multi-seed verifier).
- Dropout left on because `model.eval()` was never called in a custom loop.
