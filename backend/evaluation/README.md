# Retrieval and RAGAS Evaluation

LegalDoc AI evaluates retrieval quality separately from answer generation and also provides an end-to-end evaluation of the production document-chat path.

## Production retrieval pipeline

The document-chat path is:

~~~text
User query + document_id
            |
            +---------------------------+
            |                           |
            v                           v
Dense retrieval                   BM25 retrieval
BGE-large-en-v1.5                 BM25 Okapi
ChromaDB cosine                   Same structure-aware chunks
Top 20 chunk candidates           Top 20 chunk candidates
            |                           |
            +-------------+-------------+
                          |
                          v
                 Reciprocal Rank Fusion
                 RRF constant = 60
                 Fusion key: chunk_id
                 Top 20 fused candidates
                          |
                          v
                  Cross-Encoder
          cross-encoder/ms-marco-MiniLM-L6-v2
                          |
                          v
                 Final Top 5 chunks
                          |
                          v
                 Evidence assembly
              Chunk ID, clause ID, source span
                          |
                          v
               Gemini structured generation
                          |
                          v
                Grounded answer + citations
~~~

Dense and sparse retrieval both run over the same chunk representation. RRF is performed at chunk level using stable `chunk_id` values. It does not merge distinct chunks from a clause into one clause-level result. The cross-encoder scores every fused candidate and orders the final five evidence chunks.

The configured BGE model receives the retrieval instruction on the query embedding only. Document chunks are embedded without that query prefix. Chroma collection names include the embedding-model identifier, and collection metadata is checked against the configured model before the collection is used.

The cross-encoder's raw scores are ranking logits, not calibrated probabilities. They must not be interpreted as answer confidence.

## Strict failure policy

The production document-chat retrieval path does not silently degrade to a different algorithm.

- ChromaDB must initialize and the configured collection must be available.
- Sentence Transformers and the configured BGE model must load successfully.
- Dense queries use explicit embeddings; ChromaDB's implicit text embedding is not used.
- BM25 returns only positive-scoring candidates.
- Both retrievers are invoked for every non-empty query.
- RRF requires chunk IDs and raises on malformed candidates.
- The cross-encoder must score every fused candidate; its load and inference errors propagate.
- Indexing requires the configured embedding model and explicit embeddings.
- Chunking must preserve source offsets; chunks that cannot be mapped back to source text raise an error.
- Gemini is the generation provider for this RAG path. Gemini errors are surfaced rather than replaced by synthetic clause summaries.
- Empty retrieval produces an explicit abstention with no citations. It is not replaced by fabricated candidates.

The application-wide LLM router may remain in use by unrelated classification or explanation services. The document-chat RAG path does not use provider failover.

## Configuration

The following settings are in `backend/app/config/settings.py` and `backend/.env.example`.

| Setting | Default |
|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` |
| `EMBEDDING_QUERY_INSTRUCTION` | `Represent this sentence for searching relevant passages:` |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L6-v2` |
| `RERANKER_BATCH_SIZE` | `16` |
| `RETRIEVAL_CANDIDATE_K` | `20` |
| `RETRIEVAL_FINAL_K` | `5` |
| `RRF_K` | `60` |
| `GEMINI_MIN_REQUEST_INTERVAL_SECONDS` | `12.5` |
| `VECTOR_STORE_DIRECTORY` | `.chroma_db` |

A change to `EMBEDDING_MODEL` creates a separate model-namespaced Chroma collection. It does not reuse vectors from a different embedding model. Re-index the documents using the newly configured model before serving queries.

Gemini generation and RAGAS judge HTTP requests share a process-wide request pacer. The default interval of 12.5 seconds is conservative for a five-requests-per-minute Free Tier quota. Configure `GEMINI_MIN_REQUEST_INTERVAL_SECONDS` for the quota attached to your API project; use `0` only when your quota supports unpaced requests. The in-process pacer coordinates threads and asynchronous evaluator requests within one Python process. Multi-worker or multi-instance deployments must use a shared distributed limiter (for example, Redis) to coordinate a project-wide quota.

## Gold dataset

Create or update:

`backend/evaluation/datasets/retrieval_gold.jsonl`

Each line is one independently verified query record. Use real document and clause IDs from PostgreSQL.

Binary relevance example:

~~~json
{"query_id":"q001","document_id":"REAL_DOCUMENT_ID","query":"What is the termination notice period?","relevant_clause_ids":["REAL_CLAUSE_ID"],"answerable":true,"reference_answer":"The agreement requires 30 days written notice."}
~~~

Graded relevance example:

~~~json
{"query_id":"q002","document_id":"REAL_DOCUMENT_ID","query":"What happens after late payment?","relevance":{"CLAUSE_ID_A":3,"CLAUSE_ID_B":1},"answerable":true,"reference_answer":"The agreement defines a late-payment charge and a notice process."}
~~~

For answerable questions, supply one or more relevant clause IDs and a checked reference answer. For unanswerable questions, set `answerable` to false, provide an empty `relevant_clause_ids` list, and use a reference answer that clearly states what the document does not establish. The evaluation scripts reject inconsistent answerability labels.

Use manually reviewed labels. Include semantic paraphrases, exact legal terminology, dates, amounts, section names, multi-clause questions, and unanswerable questions. Split development and held-out test queries before tuning settings. The starter dataset is a smoke-test set, not enough evidence for production accuracy claims.

## 1. Retrieval comparison with RAGAS

This compares four retrieval variants using the same chunking and corpus:

- `dense_only`
- `bm25_only`
- `hybrid_rrf`
- `hybrid_reranked`

The hybrid RRF variant uses Top-20 from each first-stage retriever, RRF Top-20, and returns the Top-5 fused chunks. The hybrid-reranked variant adds cross-encoder scoring and returns the final Top-5 chunks. Dense-only and BM25-only return their own Top-5 rankings.

Run all variants with RAGAS Context Precision and Context Recall:

~~~bash
poetry run python backend/evaluation/run_retrieval_ragas_eval.py --top-k 5
~~~

Run deterministic IR metrics only:

~~~bash
poetry run python backend/evaluation/run_retrieval_ragas_eval.py --top-k 5 --skip-ragas
~~~

Run a small judge smoke test:

~~~bash
poetry run python backend/evaluation/run_retrieval_ragas_eval.py --top-k 5 --limit 5
~~~

RAGAS judge execution requires `GEMINI_API_KEY`. The `--skip-ragas` mode does not make a retrieval fallback; it skips judge calls and computes deterministic IR metrics only.

Outputs are written to:

- `artifacts/retrieval-ragas-evaluation/retrieval_ragas_query_results.csv`
- `artifacts/retrieval-ragas-evaluation/retrieval_ragas_summary.json`

### Retrieval metrics

| Metric | Meaning |
|---|---|
| Recall@1, @3, @5 | Fraction of relevant clauses found in the first K results |
| Precision@1, @3, @5 | Fraction of the first K returned clauses that are relevant |
| Hit Rate@1, @3, @5 | Whether at least one relevant clause appears in the first K |
| MRR@5 | Reciprocal rank of the first relevant clause, averaged across queries |
| nDCG@5 | Ranking quality using graded clause relevance |
| Context Precision | RAGAS assessment of relevant context ordering and noise |
| Context Recall | RAGAS assessment of how much reference information the retrieved context contains |
| P50/P95/P99 latency | Retrieval latency percentiles for each variant |
| Empty-result rate | Fraction of queries with no returned evidence |
| Unanswerable non-empty rate | Fraction of unanswerable queries for which a variant still returns candidate evidence |

Retrieval IR metrics are computed at clause level because the gold labels are clause IDs. Multiple returned chunks from the same clause count once for clause-level ranking. Original chunk texts remain intact for RAGAS context evaluation. Unanswerable questions are excluded from answerable-query recall and precision aggregation and are reported separately.

Metric coverage is included in the JSON summary. Failed RAGAS calls are recorded as errors and are not converted into zero-valued judge scores.

## 2. End-to-end RAGAS evaluation

This runner calls the actual production `RAGService.chat()` path. It evaluates:

- Dense retrieval
- BM25 retrieval
- RRF fusion
- Cross-encoder reranking
- Context assembly
- Gemini structured answer generation
- Citation validation

The script builds an isolated temporary ChromaDB index for the evaluation run, indexes the dataset documents with the configured BGE model, and does not persist evaluation chat messages.

Run a small smoke test:

~~~bash
poetry run python backend/evaluation/run_ragas_eval.py --top-k 5 --candidate-k 20 --limit 3
~~~

Run the complete labelled dataset:

~~~bash
poetry run python backend/evaluation/run_ragas_eval.py --top-k 5 --candidate-k 20
~~~

Outputs are written to:

- `artifacts/ragas-evaluation/ragas_query_results.csv`
- `artifacts/ragas-evaluation/ragas_summary.json`

### End-to-end metrics

| Metric | Meaning |
|---|---|
| Faithfulness | Whether answer claims are supported by retrieved context |
| Answer Relevancy | Whether the generated answer addresses the user's question |
| Answer Correctness | Semantic correctness against the reference answer |
| Context Precision | Relevance and ordering quality of retrieved evidence |
| Context Recall | Coverage of reference answer information by retrieved evidence |
| Recall@5, Precision@5, Hit Rate@5 | Deterministic clause-level retrieval quality |
| MRR@5, nDCG@5 | Clause ranking quality |
| Citation Precision/Recall | Alignment between predicted citations and gold relevant clauses |
| Citation Quote Match Rate | Whether quoted source evidence occurs in its clause |
| Citation Validity Rate | Whether citation clause IDs exist in the document |
| Citation Span Accuracy | Whether the quoted text matches the exact cited source span |
| Abstention Accuracy | Whether the system abstains on unanswerable questions |
| P50/P95/P99 chat latency | Retrieval plus Gemini answer-generation latency |

For each RAGAS metric the summary includes scored queries, eligible queries, and metric coverage. Failed judge calls are kept in query-level `metric_errors`, not silently imputed.

## 3. Legacy deterministic evaluator

The original IR-only evaluator remains available for compatibility:

~~~bash
poetry run python backend/evaluation/run_retrieval_eval.py --top-k 10
~~~

It compares the same four retriever variants and reports Recall@5/10, Precision@5/10, Hit Rate@5, MRR@10, nDCG@10, latency percentiles, and empty-result rate. Its output directory is `artifacts/retrieval-evaluation/`.

For new experiments, prefer `run_retrieval_ragas_eval.py`, which adds RAGAS judge metrics, Top-1/3/5 metrics, metric coverage, and unanswerable-query diagnostics.

## Environment and reproducibility

Install the development and evaluation dependencies:

~~~bash
poetry lock
poetry install --with dev
~~~

Set `GEMINI_API_KEY` and the retrieval settings in `backend/.env`. Before running the evaluations, ensure PostgreSQL contains the labelled documents and clauses. Evaluation creates temporary vector-store directories and will download configured Sentence Transformers models if they are not already cached.

Record the dataset version, embedding model, query instruction, cross-encoder model, Gemini model, RAGAS version, environment, and evaluator arguments with each experiment. Warm models before benchmarking latency. Repeat runs under the target deployment environment and inspect the per-query CSV; aggregate metrics alone can hide failures on dates, amounts, negations, exceptions, and multi-clause questions.

## Committed benchmark snapshot (3-query smoke test)

The committed report at `artifacts/retrieval-ragas-evaluation/retrieval_ragas_summary.json` records a smoke test over **3 queries from 1 sample document**, with `top_k=5`, `BAAI/bge-large-en-v1.5` embeddings (1024 dimensions), and `gemini-3.5-flash-lite` as the RAGAS judge.

| Retrieval variant | Recall@5 | Precision@5 | Context Precision | Context Recall | P50 latency (ms) | P95 latency (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Dense only | 1.000 | 0.200 | 0.650 | 0.667 | 266.6 | 280.5 |
| BM25 only | 1.000 | 0.200 | 0.972 | 1.000 | 3.1 | 3.8 |
| Hybrid RRF | 1.000 | 0.200 | 0.962 | 1.000 | 279.7 | 313.3 |
| Hybrid reranked | 1.000 | 0.200 | 0.962 | 1.000 | 245.9 | 254.2 |

These figures are a reproducible smoke-test snapshot, not a production benchmark. The three-query sample is too small to establish general retrieval performance. Interpret the metrics alongside the per-query CSV and a larger, manually reviewed, held-out evaluation set.

Do not report results from the starter dataset as production accuracy. Review gold labels against complete source clauses and maintain a held-out test set. RAGAS scores are evaluation estimates, not legal certification.
