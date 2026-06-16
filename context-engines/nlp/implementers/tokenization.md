---
domain: nlp-tokenization
description: Subword tokenization (BPE/WordPiece/SentencePiece) with HuggingFace tokenizers, special tokens, padding/truncation, and model alignment.
---

# Tokenization

The tokenizer is part of the model contract. Always load it from the same checkpoint as the model — mismatched vocab/special tokens silently produce garbage.

## Algorithms (know which one you have)

- **BPE** (GPT-2, RoBERTa, GPT family): merges frequent byte pairs. Byte-level BPE handles any Unicode; no `[UNK]`.
- **WordPiece** (BERT, DistilBERT): greedy longest-match, subwords prefixed with `##`. Has `[UNK]`.
- **SentencePiece / Unigram** (T5, ALBERT, XLNet, LLaMA): operates on raw text, whitespace encoded as `▁`. Language-agnostic, reversible.

## Load and use

```python
from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained("bert-base-uncased")  # use_fast=True by default

enc = tok(
    "The quick brown fox.",
    padding="max_length",      # or True (dynamic to longest in batch)
    truncation=True,
    max_length=128,
    return_tensors="pt",
)
# enc -> input_ids, attention_mask, (token_type_ids for BERT-style)
```

Prefer the **fast** (Rust) tokenizers — they give `offset_mapping` and `word_ids()`, essential for NER/QA alignment.

## Special tokens

Never hardcode `[CLS]`/`[SEP]`/`<s>`/`</s>`. Reference them:

```python
tok.cls_token, tok.sep_token, tok.pad_token, tok.eos_token, tok.pad_token_id
```

For decoder-only models (GPT, LLaMA) `pad_token` is often unset. Set it before batching:

```python
if tok.pad_token is None:
    tok.pad_token = tok.eos_token   # and resize embeddings only if you add NEW tokens
```

Adding genuinely new tokens requires resizing the model embedding table:

```python
tok.add_special_tokens({"additional_special_tokens": ["<doc>", "</doc>"]})
model.resize_token_embeddings(len(tok))
```

## Padding & truncation

- Pad **dynamically per batch** for training efficiency — use `DataCollatorWithPadding`, not `padding="max_length"`, unless you need fixed shapes (TPU/ONNX).
- `padding_side`: left for generation with decoder-only models (so the last real token is at position -1), right for encoders/classification.
- `truncation="only_second"` for pair inputs (QA, NLI) to keep the question intact.

## Alignment with subwords

`word_ids()` maps each token back to its source word. Critical for token-level labels:

```python
enc = tok(words, is_split_into_words=True, truncation=True)
word_ids = enc.word_ids()   # [None, 0, 0, 1, 2, None] -> None = special token
```

`offset_mapping` gives char spans for span extraction:

```python
enc = tok(text, return_offsets_mapping=True)
# enc["offset_mapping"] -> [(0,0), (0,3), (4,9), ...]  (0,0) marks specials
```

## Pitfalls

- **Different tokenizer than model checkpoint** → embedding lookups misaligned, model "works" but accuracy is random.
- **Cased vs uncased mismatch**: don't lowercase input for a cased model.
- **max_length too small** silently drops the end of long docs; log truncation rate.
- **Decoder-only + right padding** breaks generation; use left padding.
- **`return_tensors="pt"` with variable lengths** fails unless padding is on — collator handles this at batch time instead.
- Counting characters/words for length budgets is wrong — count **tokens** (`len(tok(text)["input_ids"])`).
