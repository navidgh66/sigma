---
domain: rl-reward-shaping
description: Reward design — sparse vs dense, potential-based shaping, and avoiding reward hacking.
---

# Reward Shaping

The reward function is the spec. Agents optimize exactly what you write, not what you mean. Most "RL doesn't work" problems are reward problems.

## Sparse vs dense

- **Sparse** (reward only at goal/success): unambiguous, hard to game, but slow/impossible to learn without exploration help. Good when correct behavior is what matters and you can afford the sample cost (or use curiosity/HER).
- **Dense** (reward each step toward goal): fast learning, but easy to misspecify — the agent optimizes the proxy, not the goal.
- Default: start sparse + correct, add shaping only if learning stalls.

## Potential-based shaping (the safe way to add density)

Plain dense rewards can change the optimal policy. **Potential-based shaping** (Ng et al. 1999) provably preserves it:

```
F(s, a, s') = γ · Φ(s') - Φ(s)
shaped_reward = r + F
```

Φ is any state potential (e.g. negative distance to goal). Because it telescopes over a trajectory, it cannot create new optimal policies — only speed up learning.

```python
def potential(state, goal):
    return -np.linalg.norm(state - goal)   # closer = higher potential

def shaped_reward(r, s, s2, goal, gamma=0.99):
    return r + gamma * potential(s2, goal) - potential(s, goal)
```

## Reward-hacking avoidance

Agents exploit any gap between proxy and intent:

- **Reward = -distance** → agent may hover near the goal without finishing (no terminal bonus). Add a terminal reward and/or step penalty.
- **Reward = forward velocity** → agent learns to fall forward / exploit physics glitches. Constrain with stability/orientation terms.
- **Reward = items collected** → agent finds an infinite respawn loop. Cap or make collection terminal.
- **Shaping too generous** → agent farms the shaping signal and ignores the real objective.

Guardrails:
- Keep the **true objective** as the dominant term; shaping should be a small nudge.
- Prefer potential-based shaping so you can't accidentally change the optimum.
- Add penalties for known degenerate behaviors (energy cost, time cost, constraint violations).
- Bound rewards to avoid one term dominating; normalize scales across terms.
- Watch for high return with low task success — the classic hacking signature.

## Practical tips

- Scale terms to comparable magnitudes; a +1000 bonus next to ±0.01 steps drowns gradients.
- Clip/normalize rewards (`VecNormalize`) for stable value learning.
- Log each reward component separately so you can see what the agent is actually chasing.
- Time penalty (small negative per step) is a cheap, effective efficiency driver.

## Pitfalls

- Hand-tuning dense rewards that silently change the optimal policy — use potential-based instead.
- No terminal reward → agent prefers to linger collecting shaping.
- Reward components on wildly different scales → one dominates.
- Adding shaping before checking whether exploration (not reward) is the bottleneck.
- Optimizing the proxy you wrote rather than verifying task success separately (see reward-hacking verifier).
