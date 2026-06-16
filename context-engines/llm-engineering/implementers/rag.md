---
domain: llm-engineering
description: Retrieval-augmented generation — chunking, embeddings, retrieval, reranking, and eval.
---

# RAG

## Pipeline
```
ingest -> chunk -> embed -> index   ||   query -> embed -> retrieve -> rerank -> generate -> cite
```

## Chunking (gets the most wrong)
- Chunk on **semantic boundaries** (headings, paragraphs), not blind fixed-size cuts that split
  sentences/tables.
- Typical: 256-512 tokens with 10-20% overlap so context isn't severed at boundaries.
- Keep metadata per chunk (source, title, section, date) for filtering + citation.
- For structured docs, preserve hierarchy (prepend section path to each chunk).
```python
from langchain_text_splitters import RecursiveCharacterTextSplitter
splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64,
            separators=["\n## ", "\n\n", "\n", ". ", " "])  # try semantic breaks first
```

## Embeddings & index
- Use a strong embedding model; keep query + doc embeddings from the SAME model/version.
- Normalize and use cosine similarity. Store vectors + metadata (pgvector, Qdrant, etc.).
- Re-embed everything when you change the model — mixed embedding spaces = garbage retrieval.

## Hybrid retrieval (better than vector alone)
```python
# Dense (semantic) + sparse (BM25/keyword) fused by Reciprocal Rank Fusion
def rrf(dense_ids, sparse_ids, k=60):
    scores = {}
    for rank, i in enumerate(dense_ids):  scores[i] = scores.get(i,0) + 1/(k+rank)
    for rank, i in enumerate(sparse_ids): scores[i] = scores.get(i,0) + 1/(k+rank)
    return sorted(scores, key=scores.get, reverse=True)
```
Dense catches paraphrase; sparse catches exact terms/IDs/codes. Hybrid beats either.

## Reranking
Retrieve top ~30 cheaply, then rerank with a cross-encoder and keep top 3-5 for the prompt.
```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("BAAI/bge-reranker-base")
ranked = sorted(zip(candidates, reranker.predict([(query, c.text) for c in candidates])),
                key=lambda x: x[1], reverse=True)[:5]
```
Reranking is the highest-ROI quality lever after fixing chunking.

## Generation with citations
- Put retrieved chunks in context with source tags; instruct the model to cite + to say
  "not in the provided context" rather than hallucinate.
- Pass only the top reranked chunks — stuffing 30 chunks degrades quality and costs more.

## Eval (RAG fails silently otherwise)
- **Retrieval**: recall@k, MRR on a labeled query->relevant-doc set.
- **Generation**: faithfulness (answer grounded in context), answer relevance, context precision
  (RAGAS-style, LLM-judged + validated).
- Test "no good context" cases — the model must abstain, not fabricate.

## Pitfalls
- Fixed-size chunking that splits tables/sentences -> incoherent retrieval.
- Query/doc embedded with different models -> mismatched space.
- Vector-only retrieval missing exact-term queries (codes, names).
- No reranking -> top-k full of near-misses.
- Stuffing too many chunks -> dilution + cost.
- No abstention instruction -> confident hallucination.

## Checklist
- [ ] Semantic chunking with overlap + metadata
- [ ] Same embedding model for query and docs
- [ ] Hybrid retrieval + cross-encoder rerank to top 3-5
- [ ] Citations + abstention instruction
- [ ] Retrieval + generation evals with a no-context test
