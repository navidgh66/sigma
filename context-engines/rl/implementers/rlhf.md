---
domain: rl-rlhf
description: RLHF for LLM alignment — reward model training, PPO fine-tuning, and the DPO alternative.
---

# RLHF (LLM Alignment)

Align an LLM to human preferences. Classic pipeline: SFT → reward model → PPO. DPO collapses the last two steps and is now the common default. Use HuggingFace **TRL**.

## Pipeline overview

1. **SFT**: supervised fine-tune on demonstration data (instruction-tuning).
2. **Reward model (RM)**: train on preference pairs (chosen vs rejected) to score responses.
3. **PPO**: fine-tune the policy to maximize RM score, with a KL penalty to the SFT model so it doesn't drift into gibberish.

## Reward model training

Preference data: `(prompt, chosen, rejected)`. RM is the base model + scalar head; loss is the Bradley-Terry ranking loss:

```python
# logits_chosen, logits_rejected = reward_model(...)  scalar per sequence
loss = -torch.nn.functional.logsigmoid(reward_chosen - reward_rejected).mean()
```

TRL `RewardTrainer` handles batching and the pairwise loss. The RM only needs to **rank**, not produce calibrated absolute scores.

## PPO for alignment (TRL PPOTrainer)

```python
from trl import PPOTrainer, PPOConfig
# objective per token: reward = RM_score - beta * KL(policy || sft_ref)
config = PPOConfig(learning_rate=1e-5, batch_size=64, mini_batch_size=8,
                   init_kl_coef=0.2, target=6.0)   # adaptive KL toward target
# loop: generate responses -> score with RM -> ppo_trainer.step(queries, responses, rewards)
```

The **KL penalty** to the frozen SFT reference is essential — without it the policy "reward hacks" the RM (degenerate, repetitive, or adversarial text that the RM happens to score high).

## DPO — skip the RM and PPO

DPO optimizes the same preference objective directly on `(prompt, chosen, rejected)` with a simple classification-style loss against a frozen reference model. No reward model, no sampling loop, far more stable.

```python
from trl import DPOTrainer, DPOConfig
# loss compares log-prob ratios of chosen vs rejected under policy vs reference,
# scaled by beta (KL strength, ~0.1). Higher beta = stay closer to reference.
trainer = DPOTrainer(model, ref_model=ref, args=DPOConfig(beta=0.1), ...)
```

DPO is the pragmatic default unless you specifically need online RL or a reusable reward model. Variants: IPO, KTO (KTO needs only binary good/bad labels, not pairs).

## Key knobs

- KL coefficient / DPO `beta`: too low → reward hacking & drift; too high → no learning.
- Reward normalization (whiten advantages) for PPO stability.
- Keep generation length bounded; length is a common hacked dimension (RM prefers longer).

## Pitfalls

- **No KL/reference anchor** → policy diverges, collapses to RM-exploiting gibberish.
- Reward model overfit to annotator quirks (length, formatting) → policy learns those, not quality.
- Preference data leakage / inconsistent labels → RM learns noise.
- PPO instability and cost — prefer DPO unless online RL is required.
- Evaluating only by RM score (the thing being gamed) instead of held-out human/judge eval.
- Reusing the policy as its own reference in DPO (must be a frozen copy).
