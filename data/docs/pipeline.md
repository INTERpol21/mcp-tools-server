# Example RAG pipeline

1. **Ingest** — split documents into ~500-token chunks with 15% overlap.
2. **Embed** — encode chunks and store vectors in Postgres (pgvector).
3. **Retrieve** — hybrid search: BM25 + cosine similarity, top-20 candidates.
4. **Rerank** — a cross-encoder narrows candidates down to top-5.
5. **Generate** — the LLM answers with citations to the retrieved chunks.

Evaluation: a nightly regression set of 50 question/answer pairs, graded
for faithfulness and answer relevance.
