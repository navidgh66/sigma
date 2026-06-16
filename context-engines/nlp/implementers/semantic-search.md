---
domain: nlp-semantic-search
description: Dense retrieval — sentence embeddings, FAISS/Qdrant indexes, cosine similarity, and cross-encoder reranking.
---

# Semantic Search

## Embeddings

Use a bi-encoder (sentence-transformers) to map text → fixed vectors. Pick by the MTEB leaderboard for your domain/size budget.

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("BAAI/bge-base-en-v1.5")     # or all-MiniLM-L6-v2 (fast, 384-d)
emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                   convert_to_numpy=True, show_progress_bar=True)
```

- **Normalize** embeddings so inner product == cosine similarity. Then use IP indexes.
- Some models need query/doc prompts (BGE: prefix queries with `"Represent this sentence for searching relevant passages: "`). Check the model card — wrong prompt tanks recall.
- Mind the **max sequence length** (often 512); chunk long docs.

## FAISS (local, fast, in-memory)

```python
import faiss, numpy as np
d = emb.shape[1]
index = faiss.IndexFlatIP(d)        # exact, cosine via normalized vectors
index.add(emb.astype("float32"))
D, I = index.search(query_emb.astype("float32"), k=10)   # D=scores, I=ids
```

Scale up with ANN: `IndexHNSWFlat` (great recall/latency, no training) or `IndexIVFFlat` (needs `.train()`, set `nprobe`). FlatIP is exact but O(N) per query.

## Qdrant (persistent, filterable, production)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
c = QdrantClient(":memory:")  # or url=...
c.create_collection("docs", vectors_config=VectorParams(size=d, distance=Distance.COSINE))
c.upsert("docs", [PointStruct(id=i, vector=v.tolist(), payload={"text": t})
                  for i, (v, t) in enumerate(zip(emb, docs))])
hits = c.query_points("docs", query=query_emb.tolist(), limit=10,
                      query_filter=None).points
```

Qdrant gives metadata filtering (date, source) alongside vector search — use it instead of filtering after retrieval.

## Reranking (two-stage retrieval)

Bi-encoder retrieves cheaply; a **cross-encoder** rescores the top-k jointly for precision.

```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
pairs = [(query, hit.payload["text"]) for hit in hits]
scores = reranker.predict(pairs)
ranked = [h for _, h in sorted(zip(scores, hits), key=lambda x: -x[0])]
```

Retrieve top-50 with the bi-encoder, rerank to top-5. This is the single biggest quality win for most RAG systems.

## Pitfalls

- **Different embedding model for queries vs index** → spaces don't align, recall collapses.
- Forgetting to normalize, then using L2 distance and calling it cosine.
- Re-embedding the corpus at query time instead of caching the index.
- Skipping query prompts that the model was trained with.
- Using exact FlatIP at million-doc scale → slow; switch to HNSW/IVF.
- Reranking the full corpus (defeats the point) — only rerank the candidate set.
- Measuring with accuracy instead of retrieval metrics: report **Recall@k**, **MRR**, **nDCG**.
