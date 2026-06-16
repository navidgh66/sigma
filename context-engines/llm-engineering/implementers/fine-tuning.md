---
domain: llm-engineering
description: When to fine-tune vs RAG vs prompt; LoRA/QLoRA supervised fine-tuning and DPO basics.
---

# Fine-Tuning

## Decision: prompt -> RAG -> fine-tune (in that order)
| Need | Reach for |
|------|-----------|
| Better instructions / format | Prompt engineering (cheapest, fastest to iterate) |
| Inject fresh/proprietary knowledge | RAG (knowledge changes, no retraining) |
| Teach a consistent style/format/behavior | Fine-tuning (SFT) |
| Align to preferences (helpful/safe/tone) | Preference tuning (DPO) |

Fine-tuning teaches **behavior and form**, not facts. For knowledge that changes, use RAG —
don't fine-tune to memorize a knowledge base.

## When fine-tuning is worth it
- You have a few hundred to thousands of high-quality, consistent examples.
- A specific output format/style/domain that prompting can't reliably hit.
- Latency/cost: distill a big-model behavior into a small fine-tuned model.

## LoRA / QLoRA (parameter-efficient SFT)
```python
from peft import LoraConfig, get_peft_model
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05,
                  target_modules=["q_proj","k_proj","v_proj","o_proj"], task_type="CAUSAL_LM")
model = get_peft_model(base_model, lora)   # trains <1% of params; adapters are tiny + swappable
```
- QLoRA = LoRA on a 4-bit quantized base -> fine-tune big models on one GPU.
- `r` (rank) 8-32 typical; higher = more capacity + more memory. Start 16.
- Format data as the model's chat template exactly; mask loss on the prompt, train on the response.
- Watch for overfitting on small sets: few epochs (1-3), eval on held-out, early stop.

## DPO (preference alignment, simpler than RLHF)
```python
# Dataset of (prompt, chosen, rejected) triples
from trl import DPOTrainer, DPOConfig
trainer = DPOTrainer(model, ref_model=None, args=DPOConfig(beta=0.1),
                     train_dataset=pref_ds, processing_class=tokenizer)
```
- DPO directly optimizes preferred over rejected responses — no separate reward model/PPO.
- `beta` controls how far the policy may drift from the reference; too high -> reward hacking/degeneration.
- Usually run SFT first, then DPO on top.

## Pitfalls
- Fine-tuning for knowledge that should be RAG -> stale + expensive to update.
- Tiny/inconsistent dataset -> overfit, catastrophic forgetting of general ability.
- Wrong chat template / not masking the prompt -> model learns to echo prompts.
- No held-out eval -> can't tell if it improved or regressed.
- Skipping prompt/RAG iteration and jumping to fine-tuning -> over-engineering.
- DPO `beta` too high -> degenerate outputs.

## Checklist
- [ ] Tried prompt + RAG first; fine-tuning justified
- [ ] Knowledge needs go to RAG, behavior/format to SFT
- [ ] Data formatted to chat template; loss masked to responses
- [ ] LoRA/QLoRA for efficiency; few epochs + held-out eval + early stop
- [ ] SFT before DPO; beta tuned to avoid degeneration
