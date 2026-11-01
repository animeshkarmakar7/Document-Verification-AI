# Strict Hybrid Retrieval and RAGAS Evaluation

## Runtime retrieval architecture

~~~text
User query + document ID
          |
          +------------------------------+
          |                              |
          v                              v
Dense retrieval                    BM25 retrieval
BGE-large-en-v1.5                  BM25 Okapi
ChromaDB cosine                    Same indexed chunk corpus
Top 20 chunks                      Top 20 chunks
          |                              |
          +--------------+---------------+
                         |
                         v
               Reciprocal Rank Fusion
               RRF constant = 60
               Fuse by chunk_id
               Keep best 20 candidates
                         |
                         v
                  Cross-Encoder
          cross-encoder/ms-marco-MiniLM-L6-v2
                         |
                         v
                 Final top 5 chunks
                         |
                         v
                 Evidence assembly
             chunk ID, clause ID, source span
                         |
                         v
              Gemini structured generation
                         |
                         v
              Grounded answer + citations
~~~

The dense query embedding uses the BGE short-query retrieval instruction; stored passage embeddings remain instruction-free. Chroma collection names include the embedding model identifier, preventing vectors from a different embedding model from sharing the same collection. Page-shard extraction chunks are stored in a separate page-extraction collection, while clause-linked chunks are stored in the clause-retrieval collection. Dense retrieval therefore only searches records carrying clause IDs and source spans. Both dense and BM25 retrieval operate over the same structure-aware clause chunks. Chunk IDs are stable across dense and lexical indexing. Fusion is performed by chunk ID, so an entire clause cannot replace the specific chunk that was ranked.

The cross-encoder receives query/chunk-text pairs and scores each candidate. Its raw scores are ranking scores, not calibrated probabilities. The cross-encoder reorders the RRF candidate set; it does not perform first-stage retrieval.

## Strict failure policy

The chat retrieval path does not silently switch to a different search method.

- ChromaDB initialization or query failures raise an error.
- The configured BGE encoder must load successfully.
- The configured embedding model is used explicitly; ChromaDB's implicit text embedding function is not used.
- BM25 candidates with zero relevance are excluded.
- Empty queries are rejected.
- RRF requires chunk IDs and fails on malformed candidates.
- The cross-encoder must load and score every fused candidate; errors propagate.
- Indexing requires the configured embedding model and explicit embeddings.
- Gemini is the only generation provider for this RAG chat path. Provider failover is not used.
- An empty retrieved set produces an explicit abstention with no citations. It does not fabricate retrieval evidence.
- A Gemini, retrieval, embedding, or reranker error is surfaced to the caller rather than replaced with a synthetic answer.
- Gemini returns clause IDs and verbatim quotes only; the application resolves quotes to exact source offsets and rejects evidence not found in the retrieved chunks.
- Gemini generation and RAGAS judge requests are paced by a shared in-process limiter. A distributed limiter is required when multiple workers share one API project quota.

The separate application-wide LLM router may still be used by unrelated classification or explanation services; the document-chat RAG path does not invoke it.

## Runtime configuration

| Setting | Default |
|---|---|
| Dense embedding model | BAAI/bge-large-en-v1.5 |
| Query embedding instruction | Represent this sentence for searching relevant passages: |
| Chroma collection namespace | Model-specific clause-retrieval collection |
| Page extraction collection | Separate model-specific collection, excluded from RAG retrieval |
| Dense vector store | ChromaDB, cosine distance |
| Sparse retriever | BM25 Okapi over the same chunks |
| Dense candidate count | 20 |
| Sparse candidate count | 20 |
| RRF constant | 60 |
| Fused candidate count | 20 |
| Cross-encoder | cross-encoder/ms-marco-MiniLM-L6-v2 |
| Cross-encoder batch size | 16 |
| Final context count | 5 |
| Gemini request interval | 12.5 seconds by default; configurable per API project quota |
| Generator | Configured Gemini model |

Settings can be overridden through the application's environment configuration. Changing the embedding model requires rebuilding the relevant ChromaDB index with that same model and dimension.

## Evaluation

Two evaluation entry points are available.

### Retrieval comparison

~~~bash
poetry run python backend/evaluation/run_retrieval_ragas_eval.py --top-k 5
~~~

This compares four retrieval variants using identical chunking and candidate-generation behavior:

- Dense only
- BM25 only
- Dense + BM25 + RRF
- Dense + BM25 + RRF + cross-encoder

The hybrid-reranked variant uses Top-20 candidates from each first-stage retriever, RRF Top-20, and final Top-5 cross-encoder output. The evaluator reports query-level CSV results and a JSON summary.

RAGAS judge metrics require GEMINI_API_KEY. To run deterministic IR metrics without the RAGAS judge:

~~~bash
poetry run python backend/evaluation/run_retrieval_ragas_eval.py --top-k 5 --skip-ragas
~~~

### End-to-end RAGAS

~~~bash
poetry run python backend/evaluation/run_ragas_eval.py --top-k 5 --candidate-k 20
~~~

This uses the same production RAGService.chat() path, including strict indexing, hybrid retrieval, cross-encoder reranking, evidence assembly, and Gemini generation. It runs against an isolated temporary ChromaDB collection and does not persist evaluation chat messages.

## Metrics

### Deterministic retrieval metrics

- Recall@1, Recall@3, Recall@5
- Precision@1, Precision@3, Precision@5
- Hit Rate@1, Hit Rate@3, Hit Rate@5
- MRR@5
- nDCG@5

Gold relevance is labelled at clause level. Retrieved chunk results are deduplicated by clause ID before clause-level IR scoring. The original chunk contexts are preserved for RAGAS context evaluation.

### RAGAS metrics

- Context Precision
- Context Recall
- Faithfulness
- Answer Correctness
- Answer Relevancy

The retrieval-only comparison computes Context Precision and Context Recall. The end-to-end evaluation computes all five metrics.

### Evidence and operations

The end-to-end report also includes citation precision, citation recall, quote match rate, abstention accuracy, P50/P95/P99 chat latency, generation mode, retrieval trace, metric error counts, and metric coverage. Unanswerable questions are evaluated separately from answerable-query recall metrics.

Metric coverage is reported as scored eligible queries divided by eligible queries. Failed RAGAS calls are not converted into zero scores.

## Reproducibility notes

Keep the gold dataset versioned and review relevant clause IDs independently. Include multiple documents, query categories, paraphrases, multi-clause questions, and unanswerable cases before treating aggregate scores as representative. Record exact embedding, cross-encoder, Gemini, RAGAS, and dataset versions with each experiment.

Cross-encoder scores are model logits and must not be interpreted as confidence probabilities. Select retrieval thresholds and acceptance gates from held-out legal-domain evaluation data rather than using universal values.
