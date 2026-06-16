---
domain: deep-learning
description: Multi-GPU training with DDP and sharded FSDP — launch, gotchas, and when to use each.
---

# Distributed Training (PyTorch)

## DDP vs FSDP
| Use DDP | Use FSDP |
|---------|----------|
| Model fits on one GPU | Model too big for one GPU |
| Want simplest scaling | Need to shard params/grads/optimizer state |
| Most CNN/medium transformers | LLMs, billions of params |

DDP replicates the model per GPU and all-reduces gradients. FSDP shards parameters,
gradients, and optimizer state across GPUs, gathering layers just-in-time.

## DDP setup
```python
import torch, os
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data.distributed import DistributedSampler

def setup():
    dist.init_process_group("nccl")
    rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(rank)
    return rank

rank = setup()
model = DDP(model.to(rank), device_ids=[rank])
sampler = DistributedSampler(train_ds, shuffle=True)
loader = DataLoader(train_ds, batch_size=bs, sampler=sampler, pin_memory=True)

for epoch in range(EPOCHS):
    sampler.set_epoch(epoch)        # REQUIRED: else every epoch shuffles identically
    for x, y in loader:
        ...                          # same loop; DDP all-reduces grads in backward
if rank == 0:
    torch.save(model.module.state_dict(), "ckpt.pt")   # .module unwraps DDP
dist.destroy_process_group()
```
Launch: `torchrun --standalone --nproc_per_node=4 train.py`

## FSDP (sharded)
```python
from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
from torch.distributed.fsdp import MixedPrecision, ShardingStrategy
mp = MixedPrecision(param_dtype=torch.bfloat16, reduce_dtype=torch.bfloat16)
model = FSDP(model, mixed_precision=mp,
             sharding_strategy=ShardingStrategy.FULL_SHARD,   # ZeRO-3 equivalent
             auto_wrap_policy=my_transformer_wrap_policy,
             device_id=torch.cuda.current_device())
# Save with FSDP state-dict context (FULL_STATE_DICT on rank 0) to avoid sharded files
```
- Use `auto_wrap_policy` to wrap transformer blocks; wrapping the whole model as one unit kills memory savings.
- Enable activation checkpointing for further memory cuts (trades compute).

## Gotchas
- **Effective batch size** = per-GPU batch × world_size. Scale LR accordingly (linear/sqrt rule).
- Metrics/loss must be `all_reduce`d before logging; otherwise you log one rank's slice.
- Only `rank == 0` should log/checkpoint/print to avoid N duplicate writes.
- BatchNorm across ranks needs `SyncBatchNorm.convert_sync_batchnorm(model)`.
- Set per-process seed = base_seed + rank carefully (data sampler handles shuffle; model init must match across ranks).
- DataLoader `num_workers` is per process — don't oversubscribe CPUs.

## Checklist
- [ ] `sampler.set_epoch(epoch)` called each epoch
- [ ] LR scaled for effective batch size
- [ ] Logging/checkpointing gated to rank 0; metrics all-reduced
- [ ] DDP saved via `model.module`; FSDP via full-state-dict context
- [ ] SyncBatchNorm if model uses BN
