---
domain: nlp-classification
description: Text classification pipeline — label encoding, metrics (F1/accuracy), and class imbalance handling.
---

# Text Classification

## Label encoding

Map labels to contiguous integers and persist the mapping in the model config.

```python
labels = sorted(df["label"].unique())
label2id = {l: i for i, l in enumerate(labels)}
id2label = {i: l for l, i in label2id.items()}
df["y"] = df["label"].map(label2id)
```

- Single-label → `AutoModelForSequenceClassification`, CrossEntropy (default).
- Multi-label → set `problem_type="multi_label_classification"`, targets are float 0/1 vectors, loss is BCEWithLogits, threshold logits at 0 (sigmoid > 0.5).

## compute_metrics

```python
import numpy as np
from sklearn.metrics import f1_score, accuracy_score, precision_recall_fscore_support

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    p, r, f1, _ = precision_recall_fscore_support(labels, preds, average="macro", zero_division=0)
    return {"accuracy": accuracy_score(labels, preds), "macro_f1": f1,
            "macro_precision": p, "macro_recall": r}
```

## Metric choice (this matters more than the model)

- **Accuracy** lies on imbalanced data — a 95%-negative dataset gets 95% by predicting all-negative.
- **Macro-F1**: unweighted mean over classes → treats rare classes as equally important. Default for imbalance.
- **Weighted-F1**: weights by support → closer to accuracy, hides minority failures.
- **Micro-F1** == accuracy for single-label.
- Report a full `classification_report` and confusion matrix, not one number.

## Class imbalance

Try in this order:

1. **Class-weighted loss** (cheapest, usually enough):

```python
import torch
from torch import nn
class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kw):
        labels = inputs.pop("labels")
        out = model(**inputs)
        loss = nn.functional.cross_entropy(out.logits, labels, weight=self.class_weights.to(out.logits.device))
        return (loss, out) if return_outputs else loss
# weights = total / (n_classes * bincount); pass via subclass attr
```

2. **Resampling**: oversample minority (risk overfit) or undersample majority (risk info loss). Stratify the split first.
3. **Focal loss** for extreme imbalance / hard examples.
4. **Threshold tuning** on the validation PR-curve instead of fixed 0.5 (multi-label / binary).

## Inference

```python
from transformers import pipeline
clf = pipeline("text-classification", model="out", top_k=None)  # top_k=None returns all scores
clf("I loved this movie")
```

## Pitfalls

- Splitting before deduping → train/test leakage inflates scores.
- Not stratifying the split → rare class absent from validation.
- Reporting accuracy on imbalanced data without F1.
- Computing weights from the full dataset including the test split (leakage).
- For multi-label, using argmax instead of per-class sigmoid threshold.
- Forgetting `zero_division=0` → metric crashes when a class has no predictions.
