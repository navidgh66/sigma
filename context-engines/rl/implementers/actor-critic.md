---
domain: rl-actor-critic
description: Off-policy actor-critic for continuous control — DDPG, TD3, SAC, entropy, soft target updates.
---

# Actor-Critic (DDPG, TD3, SAC)

Off-policy continuous-control methods. An actor outputs actions; one or two critics estimate Q. Sample-efficient (replay buffer reused). Default choice: **SAC** for robustness, **TD3** for deterministic control. Prefer SB3 implementations.

## The progression

- **DDPG**: deterministic actor + Q critic, replay buffer, target nets. Brittle — sensitive to hyperparams, overestimates Q.
- **TD3** = DDPG + three fixes: twin critics (min of two), delayed policy updates, target policy smoothing.
- **SAC**: stochastic actor + max-entropy objective (`reward + α·entropy`). Most robust; auto-tunes α.

## Soft (Polyak) target update — used by all three

```python
def soft_update(target, source, tau=0.005):
    for tp, sp in zip(target.parameters(), source.parameters()):
        tp.data.copy_(tau * sp.data + (1 - tau) * tp.data)
```

## TD3 critic target (clipped double-Q + target smoothing)

```python
with torch.no_grad():
    noise = (torch.randn_like(action) * policy_noise).clamp(-noise_clip, noise_clip)
    next_a = (actor_target(s2) + noise).clamp(-max_action, max_action)   # smoothing
    q1, q2 = critic_target(s2, next_a)
    target_q = r + gamma * (1 - done) * torch.min(q1, q2)               # min curbs overestimation
q1, q2 = critic(s, a)
critic_loss = F.mse_loss(q1, target_q) + F.mse_loss(q2, target_q)
```

Actor updated every `policy_delay` (e.g. 2) critic steps, maximizing `critic.Q1(s, actor(s))`.

## SAC essentials

```python
# Actor target uses entropy term:
with torch.no_grad():
    a2, logp2 = actor.sample(s2)            # reparameterized + tanh squash
    q1, q2 = critic_target(s2, a2)
    target_q = r + gamma * (1 - done) * (torch.min(q1, q2) - alpha * logp2)

# Actor loss maximizes Q minus entropy penalty:
a_pi, logp = actor.sample(s)
q1_pi, q2_pi = critic(s, a_pi)
actor_loss = (alpha * logp - torch.min(q1_pi, q2_pi)).mean()

# Auto-tune temperature toward target entropy = -action_dim:
alpha_loss = -(log_alpha * (logp + target_entropy).detach()).mean()
```

The tanh squash needs a log-prob correction term — getting this wrong silently breaks SAC.

## Key knobs

- `tau` 0.005, `gamma` 0.99, replay 1e6, batch 256.
- TD3: `policy_noise` 0.2, `noise_clip` 0.5, `policy_delay` 2.
- SAC: target entropy `-dim(A)`; let α auto-tune rather than fixing it.
- Normalize observations; scale/clip actions to env bounds.

## Pitfalls

- DDPG instability — reach for TD3/SAC instead of fighting it.
- Missing tanh log-prob correction in SAC → wrong entropy, policy degenerates.
- Single critic (overestimation) — use twin critics and the min.
- Updating actor every step in TD3 instead of delayed → instability.
- Hard target updates here (use soft/Polyak).
- Forgetting `(1 - done)` masking on terminal transitions.
- Action space not bounded/scaled to the env → saturated tanh, no gradient.
