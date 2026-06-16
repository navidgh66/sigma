---
domain: rl-value-based
description: Value-based deep RL — DQN, double/dueling DQN, replay buffer, target network, epsilon decay.
---

# Value-Based RL (DQN family)

DQN learns Q(s,a); the policy is `argmax_a Q(s,a)`. For discrete action spaces. Prefer SB3 `DQN` for production; roll your own only to learn or customize.

## The four load-bearing components

1. **Replay buffer** — breaks temporal correlation, enables i.i.d.-ish minibatches.
2. **Target network** — a lagged copy of Q used for bootstrap targets; stabilizes training.
3. **Epsilon-greedy** exploration with decay.
4. **Bellman target**: `y = r + γ · max_a' Q_target(s', a') · (1 - done)`.

## Replay buffer

```python
from collections import deque
import random, numpy as np, torch

class ReplayBuffer:
    def __init__(self, capacity): self.buf = deque(maxlen=capacity)
    def push(self, s, a, r, s2, done): self.buf.append((s, a, r, s2, done))
    def sample(self, n):
        s, a, r, s2, d = zip(*random.sample(self.buf, n))
        return (torch.as_tensor(np.array(s), dtype=torch.float32),
                torch.as_tensor(a), torch.as_tensor(r, dtype=torch.float32),
                torch.as_tensor(np.array(s2), dtype=torch.float32),
                torch.as_tensor(d, dtype=torch.float32))
    def __len__(self): return len(self.buf)
```

## Update step (Double DQN — use this, not vanilla)

Vanilla DQN overestimates Q because the same network selects and evaluates the max. Double DQN selects with online net, evaluates with target net:

```python
with torch.no_grad():
    next_a = q_online(s2).argmax(1, keepdim=True)            # select: online
    next_q = q_target(s2).gather(1, next_a).squeeze(1)        # evaluate: target
    y = r + gamma * next_q * (1 - done)
q = q_online(s).gather(1, a.unsqueeze(1)).squeeze(1)
loss = torch.nn.functional.smooth_l1_loss(q, y)              # Huber > MSE for stability
opt.zero_grad(); loss.backward()
torch.nn.utils.clip_grad_norm_(q_online.parameters(), 10.0)
opt.step()
```

## Target network update

```python
# hard update every C steps:
if step % target_update_freq == 0:
    q_target.load_state_dict(q_online.state_dict())
# OR soft (Polyak): θ_target ← τ θ_online + (1-τ) θ_target, τ~0.005, every step
```

## Dueling architecture

Split the head into value V(s) and advantage A(s,a), recombine:
`Q(s,a) = V(s) + (A(s,a) - mean_a A(s,a))`. Helps when action choice barely affects value.

## Epsilon decay

```python
eps = eps_end + (eps_start - eps_end) * np.exp(-step / eps_decay)  # e.g. 1.0 -> 0.05
```

Linear decay over a fixed step budget is also common and easier to reason about.

## Pitfalls

- **Updating before the buffer warms up** → overfitting to a tiny sample. Wait for `learning_starts`.
- Forgetting `(1 - done)` on terminal transitions → bootstraps past episode end, diverges.
- Using the online net for the bootstrap target (no target net) → instability.
- MSE instead of Huber → exploding loss on outlier TD errors.
- Not normalizing/stacking observations (e.g. Atari frame stacking) → partial observability.
- Too-frequent target syncs defeat the point; too-rare slows learning.
- DQN on continuous actions — wrong tool; use SAC/TD3.
