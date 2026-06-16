---
domain: nlp-ner-sequence-labeling
description: Token classification for NER — BIO/BILOU schemes, subword label alignment, and seqeval entity-level metrics.
---

# NER & Sequence Labeling

## Tagging schemes

- **BIO**: `B-PER` begins, `I-PER` continues, `O` outside. Simplest, most common.
- **BILOU/BIOES**: adds `L`/`E` (last/end) and `U`/`S` (unit/single-token). Slightly more accurate, more classes.
- Invariant: `I-X` must follow `B-X` or `I-X` of the **same** type. An `I-X` after `O` or different type is invalid.

## The core problem: subword alignment

A word splits into multiple tokens; the label belongs to the word. Align labels to subwords using `word_ids()`. Convention: label the **first** subword, set the rest to `-100` (ignored by CrossEntropy).

```python
def tokenize_and_align(examples, tok, label2id):
    enc = tok(examples["tokens"], truncation=True, is_split_into_words=True)
    all_labels = []
    for i, labels in enumerate(examples["ner_tags"]):
        word_ids = enc.word_ids(batch_index=i)
        prev, aligned = None, []
        for wid in word_ids:
            if wid is None:
                aligned.append(-100)          # special tokens
            elif wid != prev:
                aligned.append(labels[wid])   # first subword gets the label
            else:
                aligned.append(-100)          # subsequent subwords ignored
            prev = wid
        all_labels.append(aligned)
    enc["labels"] = all_labels
    return enc
```

Alternative: propagate `I-` to continuation subwords. Be consistent and document which you chose — it must match decoding.

## Model + collator

```python
from transformers import AutoModelForTokenClassification, DataCollatorForTokenClassification
model = AutoModelForTokenClassification.from_pretrained(name, num_labels=len(label2id),
                                                        id2label=id2label, label2id=label2id)
collator = DataCollatorForTokenClassification(tok)  # pads labels with -100
```

## Evaluation — use seqeval, entity-level not token-level

Token-level accuracy is inflated by the `O` majority class. seqeval scores **whole spans** — a partially correct entity counts as wrong.

```python
import numpy as np
from seqeval.metrics import classification_report, f1_score

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    true_preds, true_labels = [], []
    for pred, lab in zip(preds, labels):
        true_preds.append([id2label[p] for p, l in zip(pred, lab) if l != -100])
        true_labels.append([id2label[l] for p, l in zip(pred, lab) if l != -100])
    return {"f1": f1_score(true_labels, true_preds),
            "report": classification_report(true_labels, true_preds)}
```

seqeval expects strings with `B-`/`I-` prefixes, and uses `scheme=IOB2`/`BILOU` — pass `mode="strict", scheme=IOB2` to enforce valid sequences.

## Decoding to spans

Walk the tag sequence, open a span on `B-`, extend on matching `I-`, close on `O` or a new `B-`. Map back to char offsets via `offset_mapping`.

## Pitfalls

- Mismatched alignment (train labels first-subword, decode reads all subwords) → broken spans.
- Reporting token-level accuracy/F1 — looks great, means nothing.
- Forgetting `-100` for special tokens → model learns to predict labels for `[CLS]`/`[SEP]`.
- Orphan `I-` tags from greedy argmax; either post-process (repair) or accept seqeval penalizes them.
- Label set built from train only → unseen entity types at test crash `id2label`.
- Not handling truncation: an entity split across the 512 boundary becomes incomplete; use sliding window for long docs.
