---
domain: nlp-transformers-finetuning
description: Fine-tuning HuggingFace models with Trainer, AutoModel, LoRA/QLoRA via peft, training args, and data collators.
---

# Transformer Fine-Tuning

## Pick the right AutoModel head

```python
from transformers import AutoModelForSequenceClassification, AutoModelForTokenClassification, \
    AutoModelForSeq2SeqLM, AutoModelForCausalLM
model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=3)
```

Pass `id2label`/`label2id` so the saved config carries readable labels.

## Trainer skeleton

```python
from transformers import TrainingArguments, Trainer, DataCollatorWithPadding

args = TrainingArguments(
    output_dir="out",
    eval_strategy="epoch",
    save_strategy="epoch",
    learning_rate=2e-5,            # 1e-5..5e-5 full FT; 1e-4..3e-4 for LoRA
    per_device_train_batch_size=16,
    gradient_accumulation_steps=2, # effective batch = 16*2*num_gpus
    num_train_epochs=3,
    weight_decay=0.01,
    warmup_ratio=0.06,
    fp16=True,                     # or bf16=True on Ampere+
    load_best_model_at_end=True,
    metric_for_best_model="f1",
    seed=42,
    report_to="none",
)

trainer = Trainer(
    model=model, args=args,
    train_dataset=ds["train"], eval_dataset=ds["validation"],
    data_collator=DataCollatorWithPadding(tok),
    compute_metrics=compute_metrics,
    tokenizer=tok,
)
trainer.train()
```

`tokenize` the dataset with `dataset.map(fn, batched=True)`. Keep collator dynamic padding instead of padding in `map`.

## LoRA / QLoRA (peft)

Default for anything > ~1B params or limited VRAM. LoRA trains low-rank adapters; QLoRA adds 4-bit base weights.

```python
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import BitsAndBytesConfig
import torch

bnb = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
)
model = AutoModelForCausalLM.from_pretrained(name, quantization_config=bnb, device_map="auto")
model = prepare_model_for_kbit_training(model)

lora = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],  # check model arch
)
model = get_peft_model(model, lora)
model.print_trainable_params()   # expect <1% trainable
```

Save only adapters: `model.save_pretrained("adapter")`. Merge for deploy with `model.merge_and_unload()`.

## Key knobs

- **Effective batch size** = per_device_bs × grad_accum × num_gpus. Tune LR with it.
- **gradient_checkpointing=True** trades compute for memory; disable `use_cache` when on.
- **warmup** stabilizes early steps; 6–10% of total steps is a good default.
- Use **bf16** over fp16 on A100/H100 — no loss scaling headaches.

## Pitfalls

- Forgetting `num_labels` / `id2label` → wrong output dim or unreadable predictions.
- LoRA `target_modules` wrong for the architecture → adapters attach to nothing.
- `load_best_model_at_end=True` needs eval & save strategies to match.
- Not setting `pad_token` for causal LMs before training.
- Catastrophic forgetting from too-high LR on full FT; LoRA is more forgiving.
- Mixing quantized base with full-precision optimizer states OOMs — use paged 8-bit optimizer (`optim="paged_adamw_8bit"`).
