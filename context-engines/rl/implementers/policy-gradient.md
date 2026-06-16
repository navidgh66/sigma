---
domain: rl-policy-gradient
description: Policy gradient methods — REINFORCE, PPO clipped objective, GAE, advantage normalization.
---

# Policy Gradient (REINFORCE, PPO)

On-policy methods optimize the policy directly. PPO is the workhorse — stable, sample-efficient enough, works for discrete and continuous actions. Prefer SB3 `PPO`; implement to understand or customize.

## REINFORCE (the baseline you build from)

`∇J = E[ ∇log π(a|s) · G_t ]`, where `G_t` is the discounted return. Subtract a baseline (value estimate) to cut variance:

```python
returns = discount_cumsum(rewards, gamma)             # G_t per step
returns = (returns - returns.mean()) / (returns.std() + 1e-8)   # variance reduction
loss = -(log_probs * returns.detach()).mean()
```

REINFORCE is high-variance and on-policy — every gradient step needs fresh trajectories. PPO fixes the sample-reuse problem.

## GAE (Generalized Advantage Estimation)

Trades bias/variance in the advantage with λ:

```python
def gae(rewards, values, dones, gamma=0.99, lam=0.95):
    adv, gae_acc = torch.zeros_like(rewards), 0.0
    for t in reversed(range(len(rewards))):
        next_v = values[t + 1] if t + 1 < len(values) else 0.0
        delta = rewards[t] + gamma * next_v * (1 - dones[t]) - values[t]
        gae_acc = delta + gamma * lam * (1 - dones[t]) * gae_acc
        adv[t] = gae_acc
    returns = adv + values[:len(rewards)]
    return adv, returns
```

## PPO clipped objective

Limit how far the new policy moves from the old per update:

```python
ratio = torch.exp(new_log_probs - old_log_probs.detach())     # π_new/π_old
adv = (adv - adv.mean()) / (adv.std() + 1e-8)                  # normalize advantages
unclipped = ratio * adv
clipped = torch.clamp(ratio, 1 - eps, 1 + eps) * adv          # eps ~ 0.2
policy_loss = -torch.min(unclipped, clipped).mean()
value_loss = F.mse_loss(values, returns)
entropy_bonus = dist.entropy().mean()
loss = policy_loss + 0.5 * value_loss - 0.01 * entropy_bonus  # entropy encourages exploration
```

## Training loop shape

1. Collect a rollout batch (N steps × M envs) with the **current** policy.
2. Compute GAE advantages and returns once.
3. Do K epochs of minibatch SGD over that batch (the clip makes reuse safe).
4. Discard the batch; collect fresh (on-policy).

## Key knobs

- `clip_range` 0.1–0.3; `n_epochs` 3–10; `gae_lambda` 0.9–0.97; `ent_coef` 0.0–0.01.
- Continuous actions: Gaussian policy, learn mean (and log-std); often clip/squash actions.
- Normalize observations and (optionally) rewards (`VecNormalize`) — big stability win.

## Pitfalls

- **Not normalizing advantages** → unstable gradients.
- Reusing data for too many epochs → policy drifts past the trust region despite clipping.
- Mixing old/new log-probs incorrectly (must cache `old_log_probs` at collection time, detached).
- Forgetting `(1 - done)` bootstrap masking across episode boundaries within a rollout.
- Off-policy data fed to PPO → invalid importance ratios.
- Entropy coefficient too high → policy never sharpens; too low → premature collapse.
