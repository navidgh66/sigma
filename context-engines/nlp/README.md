# Context Engine: nlp

Deep domain knowledge for **Natural Language Processing**. (Priority domain.)

## Scope

### Foundations
- Tokenization (BPE, WordPiece, SentencePiece, Unigram), normalization, subword units
- Embeddings (word2vec, GloVe, fastText, contextual embeddings, sentence embeddings)
- Vocabulary management, OOV handling, special tokens

### Transformers & models
- HuggingFace `transformers` (AutoModel/AutoTokenizer, Trainer, pipelines)
- Encoder (BERT/RoBERTa/DeBERTa), decoder (GPT family), enc-dec (T5/BART)
- Attention mechanics, positional encodings, context windows

### Tasks
- **NLU**: text classification, NER, POS, intent detection, slot filling
- **NLG**: summarization, translation, generation, paraphrasing
- Question answering (extractive + generative), semantic search / retrieval
- Sequence labeling, span extraction, relation extraction
- Sentiment, topic modeling, text similarity

### Fine-tuning & adaptation
- Full fine-tune, LoRA/QLoRA, adapters, prompt tuning
- Data prep, label schemes (BIO/BILOU), class imbalance in text
- Domain adaptation, multilingual & cross-lingual transfer

### Pipelines & infra
- spaCy production pipelines, custom components
- Vector stores (FAISS, Qdrant, pgvector) for semantic search
- Evaluation: BLEU, ROUGE, METEOR, BERTScore, F1/exact-match, perplexity
- Inference optimization (quantization, distillation, batching, ONNX)

## Implementers
`implementers/` — tokenization, embeddings, transformers-finetuning,
classification, ner-sequence-labeling, generation-summarization,
semantic-search, multilingual, spacy-pipelines.

## Verifiers
`verifiers/` — label-scheme correctness, tokenizer/model alignment, leakage in
splits, metric appropriateness per task, eval determinism.

> 🚧 Seed file — deepen aggressively; this is a focus domain.
