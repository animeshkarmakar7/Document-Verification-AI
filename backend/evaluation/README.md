# Retrieval evaluation

The evaluator compares dense-only retrieval, BM25-style sparse retrieval, RRF fusion without the final reranker, and the current hybrid retrieval method. It reports ranking quality and retrieval latency against a manually labeled JSONL dataset.

## Dataset format

Create `backend/evaluation/datasets/retrieval_gold.jsonl`. Keep one JSON object per line.

A binary relevance record:

```json
{"query_id":"q001","document_id":"REAL_DOCUMENT_ID","query":"What is the termination notice period?","relevant_clause_ids":["REAL_CLAUSE_ID"],"answerable":true}
```

A graded relevance record:

```json
{"query_id":"q002","document_id":"REAL_DOCUMENT_ID","query":"What happens after a late payment?","relevance":{"CLAUSE_ID_A":3,"CLAUSE_ID_B":1},"answerable":true}
```

Use actual document and clause IDs from the database. A grade of 3 means highly relevant, 2 means relevant, 1 means partially relevant, and 0 means not relevant. Do not add unsupported or guessed labels. For an unanswerable question, use an empty `relevant_clause_ids` list and set `answerable` to false.

The dataset must be manually reviewed. Split development and held-out test questions before tuning retrieval parameters. Use a range of semantic paraphrases, exact legal terms, clause references, dates and amounts, multi-clause questions, and unanswerable questions.

## Run

From the repository root with dependencies and the database configured:

```bash
poetry run python backend/evaluation/run_retrieval_eval.py --dataset backend/evaluation/datasets/retrieval_gold.jsonl
```

The evaluator uses PostgreSQL for clause text and IDs and creates a fresh, isolated ChromaDB directory for each run. It does not delete or modify the application's configured ChromaDB collection. Every dataset document is indexed with the configured embedding model before evaluation. The evaluator validates embedding dimensions and stops if indexing fails or if the stored vectors do not match the model.

Outputs are written to `artifacts/retrieval-evaluation/retrieval_query_results.csv` and `artifacts/retrieval-evaluation/retrieval_summary.json`. The CSV contains per-query results and latency. The JSON contains aggregate Recall@5/10, Precision@5/10, Hit Rate@5, MRR@10, nDCG@10, p50/p95/p99 retrieval latency, and empty-result rate.

The evaluator warms the configured embedding model and ChromaDB before timed queries, so reported retrieval latency excludes initial model loading and initial vector-store access. It includes query embedding and retrieval work. With only a few questions, p95 and p99 are unstable; use at least 50–100 manually verified questions and repeat runs on the target deployment environment for representative latency. Because each run uses an isolated index, these results do not modify or replace the live application's index.

## Interpretation

Dense search returns chunks, while sparse search scores clauses. Reciprocal Rank Fusion now deduplicates each ranked list by `clause_id` before assigning ranks, so multiple chunks belonging to one clause do not count as multiple independent votes. When a clause is present in sparse results, the fused result keeps its full clause text for evidence display.

The current starter dataset has 25 questions but only a small number of unique clause labels across two documents. Treat it as a smoke test only. Because the documents have very few clauses, Precision@5/10 and Recall@10 have limited ability to distinguish systems. Verify every gold label against the full clause text, then add more complete contracts and many unique relevant clauses before making performance claims.

The `hybrid_rrf` and `hybrid_reranked` variants use the same production hybrid-search candidate generation. The lexical reranker preserves fused scores and uses lexical overlap only to break ties, so it cannot move a lower-scoring fused result above a higher-scoring one. A score tie-breaker is not a learned cross-encoder reranker; it should only be kept if held-out evaluation supports it.

Compare all variants on the same labeled queries and corpus. A higher recall means more relevant clauses were retrieved; higher MRR means the first relevant clause tends to rank earlier; higher nDCG rewards ranking highly relevant clauses near the top. Compare these gains with latency percentiles and empty-result rate.

The evaluator does not claim that hybrid retrieval is better unless measured results demonstrate it. It does not measure generated-answer correctness, citation faithfulness, or full API latency; those require a separate answer-level evaluation.
