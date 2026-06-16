---
domain: nlp-generation-summarization
description: Seq2seq generation (T5/BART) — decoding params (beam/sampling/temperature), training, and ROUGE evaluation.
---

# Generation & Summarization

## Seq2seq models

- **BART** / **PEGASUS**: encoder-decoder, strong for summarization. PEGASUS pretrained for it specifically.
- **T5 / FLAN-T5**: text-to-text, needs a task prefix (`"summarize: ..."`). FLAN variants are instruction-tuned.

## Training (Seq2SeqTrainer)

```python
from transformers import AutoModelForSeq2SeqLM, Seq2SeqTrainingArguments, Seq2SeqTrainer, \
    DataCollatorForSeq2Seq

def preprocess(ex, tok, max_in=1024, max_out=128):
    model_inputs = tok(ex["document"], max_length=max_in, truncation=True)
    labels = tok(text_target=ex["summary"], max_length=max_out, truncation=True)
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs

args = Seq2SeqTrainingArguments(
    output_dir="out", predict_with_generate=True,   # required for ROUGE during eval
    generation_max_length=128, generation_num_beams=4,
    fp16=True, learning_rate=3e-5, per_device_train_batch_size=4,
)
collator = DataCollatorForSeq2Seq(tok, model=model)  # pads labels with -100, shifts decoder inputs
```

Use `text_target=` (not a separate `tok()` call with `as_target_tokenizer`, which is deprecated). Labels padded with `-100`.

## Decoding strategies — the lever that matters at inference

```python
out = model.generate(
    **inputs,
    max_new_tokens=128,
    num_beams=4,              # beam search: deterministic, good for summarization/translation
    no_repeat_ngram_size=3,   # block repeated trigrams
    length_penalty=1.0,       # >1 favors longer, <1 shorter
    early_stopping=True,
)
```

- **Greedy** (`num_beams=1`, no sampling): fast, repetitive, lowest diversity.
- **Beam search**: best for tasks with a "correct" output (summarization, translation). Beam 4–6.
- **Sampling** (`do_sample=True`): creative/open-ended. Control with:
  - `temperature` (0.7–1.0; lower = sharper, deterministic-ish),
  - `top_k` (e.g. 50), `top_p`/nucleus (e.g. 0.9). Use top_p over top_k generally.
- Don't combine `num_beams>1` with `do_sample` casually — pick a regime.

## Evaluation — ROUGE (and watch its limits)

```python
import evaluate, numpy as np
rouge = evaluate.load("rouge")

def compute_metrics(eval_pred, tok):
    preds, labels = eval_pred
    labels = np.where(labels != -100, labels, tok.pad_token_id)   # restore pad before decode
    dp = tok.batch_decode(preds, skip_special_tokens=True)
    dl = tok.batch_decode(labels, skip_special_tokens=True)
    return rouge.compute(predictions=dp, references=dl, use_stemmer=True)
```

- ROUGE-1/2 = unigram/bigram overlap recall; ROUGE-L = longest common subsequence.
- For abstractive quality also report **BERTScore**; ROUGE misses paraphrase. Faithfulness (no hallucination) needs separate checks.

## Pitfalls

- Forgetting `predict_with_generate=True` → eval scores teacher-forced loss, not generation quality.
- Not replacing `-100` with `pad_token_id` before `batch_decode` → decode crashes / garbage.
- T5 without the task prefix → degraded output.
- `max_new_tokens` too small truncates summaries; too large invites repetition — pair with `no_repeat_ngram_size`.
- Comparing ROUGE across papers with different tokenization/stemming — settings must match.
- Sampling at eval makes metrics non-deterministic; use beam/greedy for reported numbers, fix the seed otherwise.
