---
domain: rl-verify-reward-correctness
description: Verify reward computation, discounting, return calculation, and bootstrap masking — no off-by-one.
---

# Verifier: Reward & Return Correctness

Subtle bugs here (off-by-one, wrong discount, bad terminal masking) silently bias learning while training "runs fine". Verify the math against ground truth.

## Checks

1. **Reward timing.** `step(a)` returns the reward for the transition `s --a--> s'`, attributed to time t. No off-by-one shift between action and its reward.
2. **terminated vs truncated.** Bootstrap is masked on `terminated` (true episode end) but **not** on `truncated` (time limit) — the value should still be bootstrapped for truncation.
3. **Discount applied correctly.** `G_t = Σ γ^k r_{t+k}`. Verify against a hand-computed example.
4. **No future leakage.** Returns at t use only rewards from t onward.
5. **Episode boundaries reset accumulators** in multi-episode rollouts.

## Reference return calculation

```python
def discounted_returns(rewards, dones, gamma):
    """G_t = r_t + gamma * G_{t+1} * (1 - done_t)"""
    returns, g = [0.0] * len(rewards), 0.0
    for t in reversed(range(len(rewards))):
        g = rewards[t] + gamma * g * (1 - dones[t])
        returns[t] = g
    return returns
```

## Ground-truth unit test

```python
# rewards [1, 1, 1], no terminal until end, gamma=0.9
# G_2 = 1
# G_1 = 1 + 0.9*1 = 1.9
# G_0 = 1 + 0.9*1.9 = 2.71
r = discounted_returns([1, 1, 1], [0, 0, 1], 0.9)
assert abs(r[0] - 2.71) < 1e-9 and abs(r[1] - 1.9) < 1e-9 and abs(r[2] - 1.0) < 1e-9
```

## Bootstrap target check (TD)

```python
# terminal transition must NOT bootstrap:
y_terminal = r + gamma * next_q * (1 - done)   # done=1 -> y = r  ✓
assert (compute_target(r=5.0, next_q=100.0, done=1, gamma=0.99) == 5.0)
# truncation: done passed to the target should be `terminated`, not `terminated or truncated`
```

## GAE sanity

With `lambda=1`, GAE advantages + values should equal Monte-Carlo returns. With `lambda=0`, advantage == one-step TD error. Test both endpoints.

## Verdict criteria

- **PASS**: returns match hand-computed values, terminal masking uses `terminated` only, no off-by-one, discount correct, GAE endpoints check out.
- **WARN**: discount or λ outside typical range without justification, or rewards unnormalized at large scale (works but fragile).
- **FAIL**: reward attributed to wrong timestep, bootstrap masked on `truncated`, future reward leakage, accumulator not reset across episodes, or hand-computed return mismatch.

## Common findings

- `done = terminated or truncated` fed into the bootstrap mask → value learning biased at time limits.
- Return computed forward (not reversed) with wrong accumulation.
- Reward indexed `r[t+1]` instead of `r[t]` — off-by-one shifts credit.
- Multi-env rollout sharing one running return accumulator across resets.
