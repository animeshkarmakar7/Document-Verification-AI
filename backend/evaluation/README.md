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

To upsert the clauses for the dataset's documents before evaluating:

```bash
poetry run python backend/evaluation/run_retrieval_eval.py --dataset backend/evaluation/datasets/retrieval_gold.jsonl --index-missing
```

The evaluator uses the configured ChromaDB directory and PostgreSQL database. Run it against a stable corpus and avoid indexing while ingestion is modifying the same documents. The dense-only and hybrid variants require the vector index to contain chunks for the evaluated documents.

Outputs are written to `artifacts/retrieval-evaluation/retrieval_query_results.csv` and `artifacts/retrieval-evaluation/retrieval_summary.json`. The CSV contains per-query results and latency. The JSON contains aggregate Recall@5/10, Precision@5/10, Hit Rate@5, MRR@10, nDCG@10, p50/p95/p99 retrieval latency, and empty-result rate.

The latency measurement starts after service initialization, so it excludes model loading and database startup. It includes query embedding and retrieval work. Run multiple times on the target deployment environment for representative production latency.

## Interpretation

Compare all variants on the same labeled queries and corpus. A higher recall means more relevant clauses were retrieved; higher MRR means the first relevant clause tends to rank earlier; higher nDCG rewards ranking highly relevant clauses near the top. Compare these gains with latency percentiles and empty-result rate.

The evaluator does not claim that hybrid retrieval is better unless measured results demonstrate it. It does not measure generated-answer correctness, citation faithfulness, or full API latency; those require a separate answer-level evaluation.
