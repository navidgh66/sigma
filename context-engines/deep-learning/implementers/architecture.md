---
domain: deep-learning
description: Building CNN, RNN, and Transformer blocks in PyTorch with correct shapes and norm placement.
---

# Architecture (PyTorch)

## nn.Module skeleton
```python
import torch, torch.nn as nn
class Net(nn.Module):
    def __init__(self, in_dim, hidden, n_classes):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden), nn.GELU(), nn.Dropout(0.1),
            nn.Linear(hidden, n_classes),
        )
    def forward(self, x):            # x: (B, in_dim)
        return self.net(x)           # logits, NOT softmax — loss applies it
```
Return raw logits; `CrossEntropyLoss` expects logits (it fuses log_softmax + NLL).

## CNN block
```python
class ConvBlock(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.conv = nn.Conv2d(cin, cout, 3, padding=1, bias=False)  # bias off before BN
        self.bn   = nn.BatchNorm2d(cout)
        self.act  = nn.ReLU(inplace=True)
    def forward(self, x):            # x: (B, C, H, W)
        return self.act(self.bn(self.conv(x)))
# Order: Conv -> Norm -> Activation. Pool/stride to downsample. GlobalAvgPool before head.
```

## RNN / LSTM
```python
self.lstm = nn.LSTM(input_size, hidden, num_layers=2, batch_first=True,
                    bidirectional=True, dropout=0.2)
# x: (B, T, F). out: (B, T, hidden*2). Use pack_padded_sequence for variable lengths.
out, (h, c) = self.lstm(x)
```
- `batch_first=True` keeps shapes intuitive `(B, T, F)`.
- Pack padded sequences so padding doesn't pollute hidden states.
- Prefer Transformers over RNNs for new work unless streaming/very-long is constrained.

## Transformer encoder block
```python
class Block(nn.Module):
    def __init__(self, d, heads, mlp=4):
        super().__init__()
        self.ln1 = nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, heads, batch_first=True)
        self.ln2 = nn.LayerNorm(d)
        self.mlp = nn.Sequential(nn.Linear(d, mlp*d), nn.GELU(), nn.Linear(mlp*d, d))
    def forward(self, x, mask=None):                 # x: (B, T, d)
        x = x + self.attn(self.ln1(x), self.ln1(x), self.ln1(x),
                          key_padding_mask=mask)[0]   # pre-norm + residual
        x = x + self.mlp(self.ln2(x))
        return x
```
- **Pre-norm** (LayerNorm before sublayer) trains far more stably than post-norm.
- Add positional encoding/embeddings; attention is permutation-invariant without them.
- `key_padding_mask` (B, T) True=ignore for padded tokens; causal mask for autoregressive.

## Pitfalls
- Applying softmax then CrossEntropyLoss -> double softmax, broken gradients.
- BatchNorm with batch size 1 or under heavy distribution shift -> use GroupNorm/LayerNorm.
- Forgetting positional info in Transformers.
- Shape bugs: print `.shape` at each stage; (B, C, H, W) for conv, (B, T, F) for sequence.
- `inplace=True` ops can break autograd if the tensor is needed for backward — drop if errors.

## Checklist
- [ ] Model outputs logits matching loss expectation
- [ ] Norm placement correct (pre-norm transformers; conv->bn->act)
- [ ] Positional encoding present for transformers
- [ ] Padding masked in attention/RNN
- [ ] Shapes verified end to end
