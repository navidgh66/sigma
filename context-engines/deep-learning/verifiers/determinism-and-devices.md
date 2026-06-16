---
domain: deep-learning
description: PASS/WARN/FAIL verifier for seeding, device placement, and train/eval mode correctness in PyTorch.
---

# Verifier: Determinism & Devices

## Seeding / reproducibility
```python
import torch, numpy as np, random, os
def seed_everything(seed=42):
    random.seed(seed); np.random.seed(seed)
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
# For strict determinism (slower):
torch.use_deterministic_algorithms(True)
torch.backends.cudnn.benchmark = False
# DataLoader: pass worker_init_fn + a seeded generator
```

## FAIL (block)
- **F1**: no global seed set anywhere; runs are non-reproducible.
- **F2 device mismatch**: tensors/model on different devices — `model.cuda()` but batch left on CPU,
  or `.to(device)` missing on inputs/targets. Grep loops for `.to(device)` on both x and y.
- **F3 missing eval mode**: validation/inference run without `model.eval()` -> Dropout active,
  BatchNorm uses batch stats -> wrong, unstable metrics.
- **F4 missing train mode**: training after an eval phase without `model.train()` restored.
- **F5 grad in eval**: validation/inference loop without `torch.no_grad()` (or `inference_mode`) ->
  memory blowup, possible accidental graph retention.
- **F6**: optimizer created over params from a model copied/moved to device AFTER optimizer init
  (param tensors no longer match) — always `.to(device)` then build optimizer.

## WARN (justify or fix)
- **W1**: `cudnn.benchmark=True` while claiming reproducibility (it autotunes nondeterministically).
- **W2**: DataLoader `num_workers>0` without `worker_init_fn`/generator seeding -> nondeterministic order.
- **W3**: seed set but `use_deterministic_algorithms` off where exact reproduction is required.
- **W4**: `.item()`/`.cpu()` calls inside the hot training loop (perf + sync), not a correctness fail.
- **W5**: device hardcoded to `"cuda"` with no CPU fallback — breaks on CPU-only machines.
- **W6**: mixing `model.eval()` with manually-frozen BatchNorm without `requires_grad` checks.

## PASS
- One `seed_everything()` call at start; seeds cover random/numpy/torch/cuda.
- Single `device` variable; model and every batch `.to(device)`.
- `model.train()` and `model.eval()` toggled around each phase explicitly.
- Validation/inference wrapped in `torch.no_grad()`.
- Optimizer built after model is on its final device.

## Smoke test
```python
seed_everything(0); out1 = model(fixed_batch.to(device))
seed_everything(0); out2 = model(fixed_batch.to(device))
assert torch.allclose(out1, out2), "Nondeterministic forward — check seeds/cudnn"
assert next(model.parameters()).device == fixed_batch.to(device).device, "Device mismatch"
```

## Verdict format
```
DETERMINISM & DEVICES: WARN
- F3 fixed: model.eval() added before val loop (line 88)
- W2: DataLoader workers unseeded — add worker_init_fn for reproducible order
```
