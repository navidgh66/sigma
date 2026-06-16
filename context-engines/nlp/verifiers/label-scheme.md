---
domain: nlp-verify-label-scheme
description: Verify BIO/BILOU tag sequences are well-formed — no orphan I- tags, valid transitions, consistent type sets.
---

# Verifier: Label Scheme Correctness

Goal: confirm the tag sequences (gold and predicted) obey the chosen scheme's grammar. Invalid sequences mean broken alignment, bad decoding, or a mislabeled dataset.

## What to check

1. **Scheme is declared and consistent.** One of BIO(IOB2), BIOES/BILOU. The same scheme must be used in labeling, training alignment, and seqeval decoding.
2. **No orphan `I-` tags.** Every `I-X` must be preceded by `B-X` or `I-X` of the **same type**. An `I-X` at sequence start, after `O`, or after a different type is invalid.
3. **BILOU/BIOES extra rules:** `L-X`/`E-X` only after `B-X`/`I-X` same type; `U-X`/`S-X` stand alone; `B-X` must eventually close with `L-X`/`E-X`.
4. **Type set closure.** Predicted types ⊆ training types. No `I-` without a matching `B-` type in the label map.
5. **Special-token labels** are `-100` (ignored), never a real class.

## Validation snippet

```python
def validate_bio(tags):
    """Return list of (index, message) violations for an IOB2 sequence."""
    errors, prev_type = [], None
    for i, t in enumerate(tags):
        if t == "O":
            prev_type = None
            continue
        prefix, _, typ = t.partition("-")
        if prefix == "B":
            prev_type = typ
        elif prefix == "I":
            if prev_type != typ:
                errors.append((i, f"orphan {t}: prev_type={prev_type}"))
            prev_type = typ
        else:
            errors.append((i, f"bad prefix {t}"))
    return errors
```

Run over the whole gold set and over a sample of model predictions:

```python
bad = [(j, validate_bio(seq)) for j, seq in enumerate(all_tag_seqs)]
bad = [(j, e) for j, e in bad if e]
assert not bad, f"{len(bad)} sequences violate BIO: {bad[:5]}"
```

For strict scheme enforcement, lean on seqeval:

```python
from seqeval.scheme import IOB2
from seqeval.metrics import classification_report
classification_report(gold, pred, mode="strict", scheme=IOB2)  # raises/penalizes invalid
```

## Verdict criteria

- **PASS**: gold set has zero violations; predicted violation rate is low or repaired in post-processing; scheme consistent end to end.
- **WARN**: predictions contain orphan `I-` tags from raw argmax but a documented repair step (Viterbi/greedy-fix) follows.
- **FAIL**: gold labels violate the scheme, scheme differs between train and eval, or `-100` not used for specials.

## Common findings

- Gold dataset uses IOB1 (`I-` starts spans) but code assumes IOB2 → systematic shift.
- Subword alignment labeled continuation tokens with `B-` instead of `I-`/`-100`.
- Type present in predictions but absent from `label2id` → KeyError at decode.
- Truncated docs leave a `B-` with no closing tag at the 512 boundary.
