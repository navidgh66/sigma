# Context Engine: deep-learning

Domain knowledge for **deep learning** with PyTorch / TensorFlow.

## Scope
- Model architectures (CNN, RNN/LSTM/GRU, Transformers, autoencoders)
- Training loops (optimizers, schedulers, mixed precision, gradient clipping)
- Data loading (`Dataset`/`DataLoader`, augmentation, sharding)
- CUDA / device management, OOM debugging
- Distributed training (DDP, FSDP, multi-GPU, multi-node)
- Regularization (dropout, weight decay, early stopping, label smoothing)
- Model serving (TorchScript, ONNX, Triton, TorchServe)
- Reproducibility (seeds, deterministic ops)

## Implementers
`implementers/` — architecture, training-loop, data-loading, distributed-training,
serving.

## Verifiers
`verifiers/` — gradient sanity, device placement, seed determinism, checkpoint
integrity, eval/train mode correctness.

> 🚧 Seed file.
