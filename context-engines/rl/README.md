# Context Engine: rl

Deep domain knowledge for **Reinforcement Learning**. (Priority domain.)

## Scope

### Foundations
- MDP formulation (states, actions, rewards, transitions, discount)
- Value-based (Q-learning, DQN + variants: double, dueling, prioritized replay)
- Policy gradient (REINFORCE, A2C/A3C, PPO, TRPO)
- Actor-critic (SAC, TD3, DDPG)
- Model-based RL, planning, world models

### Environments
- Gymnasium / Gym API, custom environment design
- Vectorized envs, wrappers, observation/action space design
- Reward shaping, curriculum learning, sparse-reward strategies

### Advanced
- Multi-agent RL (MARL): cooperative, competitive, self-play
- Offline RL (CQL, IQL, behavior cloning, dataset curation)
- **RLHF** (reward modeling, PPO for LLM alignment, DPO as alternative)
- Exploration strategies (ε-greedy, UCB, intrinsic motivation, RND)
- Hierarchical RL, options framework

### Infra & tooling
- Ray RLlib, Stable-Baselines3, CleanRL patterns
- Experiment tracking for RL (wandb, tensorboard), seed/variance reporting
- Distributed rollouts, replay buffers, GPU-accelerated envs

### Evaluation
- Sample efficiency, asymptotic performance, variance across seeds
- Evaluation protocols (deterministic eval, multiple seeds, confidence intervals)
- Common pitfalls (reward hacking, instability, off-by-one in returns)

## Implementers
`implementers/` — mdp-formulation, value-based, policy-gradient, actor-critic,
environment-design, reward-shaping, multi-agent, offline-rl, rlhf, ray-rllib.

## Verifiers
`verifiers/` — reward correctness, multi-seed reporting, eval-protocol soundness,
replay-buffer integrity, reward-hacking checks.

> 🚧 Seed file — deepen aggressively; this is a focus domain.
