---
domain: nlp-verify-tokenizer-alignment
description: Verify the tokenizer matches the model checkpoint, special tokens line up, and no silent length mismatches.
---

# Verifier: Tokenizer–Model Alignment

A model is only valid with the tokenizer it was trained with. This verifier catches the silent failure where everything runs but predictions are random because the vocab/specials/lengths don't line up.

## Checks

1. **Same source checkpoint.** Tokenizer and model loaded from the same name/path (or the tokenizer saved alongside the fine-tuned model).
2. **Vocab size == embedding rows.** `model.config.vocab_size == len(tokenizer)`. If new tokens were added, `resize_token_embeddings` must have been called.
3. **Special token IDs consistent.** `pad`, `eos`, `bos`, `cls`, `sep`, `unk` exist where the architecture needs them and IDs map within vocab.
4. **max_length within model limit.** `max_length <= model.config.max_position_embeddings` (e.g. 512 BERT, 1024 GPT-2). Longer silently errors or truncates.
5. **Padding side correct for the head.** Left for decoder-only generation; right for encoders.
6. **Truncation reporting.** Measure how many inputs exceed `max_length` — a high rate means lost content.

## Verification snippet

```python
def check_alignment(tok, model, max_length, sample_texts):
    issues = []
    if len(tok) != model.config.vocab_size:
        issues.append(f"vocab mismatch: tokenizer={len(tok)} model={model.config.vocab_size}")

    limit = getattr(model.config, "max_position_embeddings", None)
    if limit and max_length > limit:
        issues.append(f"max_length {max_length} > model limit {limit}")

    if model.config.is_encoder_decoder is False and getattr(model.config, "is_decoder", False):
        if tok.padding_side != "left":
            issues.append("decoder-only model should pad left for generation")

    if tok.pad_token_id is None:
        issues.append("pad_token unset")

    lens = [len(tok(t)["input_ids"]) for t in sample_texts]
    trunc = sum(l > max_length for l in lens)
    if trunc:
        issues.append(f"{trunc}/{len(lens)} samples exceed max_length (p95={sorted(lens)[int(.95*len(lens))-1]})")

    # round-trip sanity
    ids = tok("alignment check", return_tensors="pt")["input_ids"]
    assert ids.max().item() < model.config.vocab_size, "token id out of embedding range"
    return issues
```

## Verdict criteria

- **PASS**: vocab == embeddings, specials present and in-range, max_length ≤ limit, padding side correct, truncation rate acceptable for the task.
- **WARN**: notable truncation rate (>5–10%) for long-doc tasks, or `pad_token = eos_token` reused without embedding resize (fine, but note it).
- **FAIL**: vocab/embedding mismatch, token id ≥ vocab_size (would index out of bounds), max_length over model limit, missing required special token, wrong padding side for generation.

## Common findings

- Fine-tuned model directory missing the tokenizer files → loading falls back to a different tokenizer.
- Added domain tokens without `resize_token_embeddings` → out-of-range embedding lookup.
- max_length 1024 on a 512-position model → runtime error or silent truncation.
- Right-padded decoder-only inputs → generation reads pad tokens as context.
