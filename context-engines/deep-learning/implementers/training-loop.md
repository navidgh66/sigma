---
domain: deep-learning
description: Robust PyTorch training loop with optimizer, scheduler, AMP, grad clipping, and checkpointing.
---

# Training Loop (PyTorch)

## Canonical loop
```python
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=0.01)
sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-4,
            steps_per_epoch=len(train_loader), epochs=EPOCHS)
scaler = torch.amp.GradScaler("cuda")
crit = torch.nn.CrossEntropyLoss()

for epoch in range(EPOCHS):
    model.train()
    for x, y in train_loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        opt.zero_grad(set_to_none=True)            # set_to_none is faster
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = crit(model(x), y)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)                       # unscale BEFORE clipping
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt)
        scaler.update()
        sched.step()                               # OneCycle steps per batch
```

## Optimizer & LR
- **AdamW** default for transformers/most nets; SGD+momentum (0.9) + nesterov for CNNs/vision.
- Decouple weight decay (AdamW does); don't decay biases/LayerNorm params (use param groups).
- LR is the most important knob. Use a finder or start AdamW@3e-4, SGD@0.1.

## Schedulers
- `OneCycleLR` (warmup+anneal, step per batch) — strong general default.
- `CosineAnnealingLR` / cosine-with-warmup — standard for transformers.
- `ReduceLROnPlateau` (step per epoch on val metric) when no schedule budget known.
- Match `.step()` cadence to the scheduler (per-batch vs per-epoch) — a common bug.

## AMP (mixed precision)
- bf16 (Ampere+) needs no GradScaler and is more stable; fp16 needs GradScaler.
- Wrap only forward+loss in `autocast`; keep loss reduction in fp32.

## Validation + checkpointing
```python
model.eval()
with torch.no_grad():
    val_loss = sum(crit(model(x.to(device)), y.to(device)) for x, y in val_loader)
torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
            "sched": sched.state_dict(), "scaler": scaler.state_dict(),
            "epoch": epoch, "best": best_metric}, "ckpt.pt")
```
- Save the full state (model+opt+sched+scaler+epoch) to resume exactly.
- Keep best-by-val-metric separate from last checkpoint. Early-stop on val plateau.

## Pitfalls
- Forgetting `model.train()` / `model.eval()` -> BatchNorm/Dropout misbehave.
- Forgetting `optimizer.zero_grad()` -> gradients accumulate across steps.
- Clipping before `scaler.unscale_` -> clips scaled grads (wrong threshold).
- `loss.item()` inside the hot loop forces a GPU sync every step; accumulate on device.
- Computing accuracy without `torch.no_grad()` leaks memory via the graph.

## Checklist
- [ ] train()/eval() toggled around each phase
- [ ] zero_grad each step; clip after unscale
- [ ] scheduler step cadence matches its type
- [ ] full state checkpointed for resume; best tracked separately
- [ ] no per-step GPU syncs in hot path
