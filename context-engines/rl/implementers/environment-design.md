---
domain: rl-environment-design
description: Gymnasium API — custom envs, observation/action spaces, wrappers, and the reset/step contract.
---

# Environment Design (Gymnasium)

Use **Gymnasium** (the maintained fork of Gym). The env is the contract every algorithm depends on — get the spaces and the step/reset signatures exactly right or training silently breaks.

## The contract (Gymnasium >= 0.26)

- `reset(seed=None, options=None) -> (obs, info)`
- `step(action) -> (obs, reward, terminated, truncated, info)`
  - **terminated**: episode ended by MDP (goal/failure). Bootstrap stops here.
  - **truncated**: ended by time limit / external cutoff. Still bootstrap the value.
  - Do **not** merge these into one `done` — they're treated differently in returns.

## Custom env skeleton

```python
import gymnasium as gym
from gymnasium import spaces
import numpy as np

class GridEnv(gym.Env):
    metadata = {"render_modes": ["human"], "render_fps": 4}

    def __init__(self, size=5, render_mode=None):
        super().__init__()
        self.size = size
        self.observation_space = spaces.Box(low=0, high=size - 1, shape=(2,), dtype=np.float32)
        self.action_space = spaces.Discrete(4)            # 0=up 1=down 2=left 3=right
        self.render_mode = render_mode

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)                           # seeds self.np_random
        self.pos = self.np_random.integers(0, self.size, size=2).astype(np.float32)
        self.goal = np.array([self.size - 1, self.size - 1], dtype=np.float32)
        return self._obs(), {}

    def step(self, action):
        delta = {0: (0, 1), 1: (0, -1), 2: (-1, 0), 3: (1, 0)}[int(action)]
        self.pos = np.clip(self.pos + delta, 0, self.size - 1).astype(np.float32)
        terminated = bool(np.array_equal(self.pos, self.goal))
        reward = 1.0 if terminated else -0.01             # step penalty drives efficiency
        truncated = False                                 # let a TimeLimit wrapper handle it
        return self._obs(), reward, terminated, truncated, {}

    def _obs(self): return self.pos.copy()
```

## Spaces

- `Box` (continuous / vector), `Discrete` (single int), `MultiDiscrete`, `MultiBinary`, `Dict`/`Tuple` (composite).
- Match `dtype` to what your network expects (`float32` obs, `int64` discrete actions).
- Bound `Box` realistically — algorithms scale to the declared bounds.

## Wrappers (compose, don't bake in)

```python
from gymnasium.wrappers import TimeLimit, NormalizeObservation, RecordEpisodeStatistics, ClipAction
env = TimeLimit(GridEnv(), max_episode_steps=100)      # sets truncated
env = RecordEpisodeStatistics(env)                     # info["episode"] on done
env = NormalizeObservation(env)                        # running mean/std
```

Vectorize for throughput: `gym.make_vec(id, num_envs=8)` or SB3 `SubprocVecEnv`.

## Validate

```python
from gymnasium.utils.env_checker import check_env
check_env(GridEnv())   # catches space/dtype/return-signature bugs
```

## Pitfalls

- **Old 4-tuple `done`** instead of `(terminated, truncated)` → time-limit episodes wrongly stop bootstrapping, biasing the value function.
- Returning obs outside the declared `observation_space` → NaNs, silent divergence.
- Not seeding via `super().reset(seed=seed)` → non-reproducible rollouts.
- Mutable obs returned by reference (return `.copy()`).
- Reward and termination logic entangled — keep shaping in a wrapper, not the core dynamics.
- Forgetting `RecordEpisodeStatistics` then hand-rolling buggy episode-return tracking.
