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


## End-to-end chatbot evaluation with Ragas

The Ragas runner evaluates the actual `RAGService.chat()` path. It records the answer and retrieved contexts without adding evaluation turns to chat history, and builds an isolated ChromaDB index for the run. It does not delete or alter the application's regular vector index.

Install the evaluation dependencies after pulling the repository changes:

```powershell
poetry lock
poetry install --with dev
```

Confirm `GEMINI_API_KEY` is set in `backend/.env`. The configured Gemini model is used by LegalDocAI and, by default, by Ragas as the evaluation judge. Google Gemini embeddings are used by the embedding-dependent Ragas metrics. The evaluation judge makes additional model/API calls, so start with a small number of questions.

Run a small smoke test first:

```powershell
poetry run python backend/evaluation/run_ragas_eval.py --limit 3
```

Then evaluate the full labelled dataset:

```powershell
poetry run python backend/evaluation/run_ragas_eval.py
```

The dataset must contain `reference_answer`, `answerable`, and `relevant_clause_ids` for every question. Reference answers should be checked against the full source clauses; answers drafted from short previews are not reliable ground truth. Keep both answerable and unanswerable questions in the dataset.

The runner evaluates Faithfulness, Context Precision, Context Recall, Answer Correctness, and Answer Relevancy using the current Ragas collections API. Context Precision and Context Recall are not scored for unanswerable questions. It also computes deterministic citation-ID precision/recall, whether quoted citation text appears in the stored clause text, abstention accuracy, and end-to-end chatbot latency.

Results are written to `artifacts/ragas-evaluation/ragas_query_results.csv` and `artifacts/ragas-evaluation/ragas_summary.json`. Review the per-question CSV alongside the aggregate JSON. A Ragas metric error is recorded per query in `metric_errors`; do not interpret a metric with too few successful scores as a valid aggregate.

The current 30-row dataset covers only two documents and has draft reference answers based on an exported preview. It is suitable for checking the evaluation plumbing, not for making production accuracy claims. Verify each reference against the full clauses and build a held-out set spanning many complete contracts before reporting system performance.

The judge model is currently the same configured model as the chatbot unless `--judge-model` is supplied. For stronger evaluation, use a separate capable judge model where available and manually audit a sample of Ragas judgements. Ragas scores are evaluator estimates, not legal certification.

---

## Retrieval Ragas Evaluation (Document Processing / Hybrid Retrieval Evidences)

To generate concrete empirical evidence comparing all 4 retrieval techniques (`dense_only`, `bm25_only`, `hybrid_rrf`, and production `hybrid_reranked`) on both deterministic IR metrics and LLM-judged RAGAS retrieval metrics without requiring chatbot generation:

```powershell
# Quick IR-only run (deterministic metrics, no LLM API calls, instant):
poetry run python backend/evaluation/run_retrieval_ragas_eval.py --skip-ragas

# Complete run with Ragas Context Precision & Context Recall (using Gemini judge):
poetry run python backend/evaluation/run_retrieval_ragas_eval.py --limit 5

# Full dataset run:
poetry run python backend/evaluation/run_retrieval_ragas_eval.py
```

### Metrics Reported as Empirical Evidence

| Metric | Source | What it Measures |
|---|---|---|
| **Context Precision** | Ragas / LLM | Signal-to-noise ratio in retrieved text; rewards placing relevant information at higher ranks. |
| **Context Recall** | Ragas / LLM | Coverage of ground-truth reference answer facts by the retrieved context. |
| **MRR@10** | Deterministic IR | Mean Reciprocal Rank (1/rank) of the first relevant clause retrieved. |
| **nDCG@10** | Deterministic IR | Position-discounted cumulative gain for graded legal relevance. |
| **Recall@5 / Recall@10** | Deterministic IR | Proportion of all relevant clauses captured in top-K results. |
| **HitRate@5** | Deterministic IR | Binary indication of whether at least one relevant clause was returned in top-5. |
| **Retrieval Latency (p50/p95/p99)** | System | Micro-benchmarked retrieval latency in milliseconds. |

### Production Reliability Features Built-in

1. **Context Deduplication & Caching**: When variants (e.g. `hybrid_rrf` vs `hybrid_reranked`) retrieve identical contexts for a query, the LLM evaluation is cached and reused, reducing LLM API consumption by up to 75%.
2. **Adaptive 429 Rate-Limit Backoff**: Automatically reads `Retry-After` headers and applies exponential backoff when encountering Google AI Studio API rate limits.
3. **Isolated Evaluation Index**: Each run builds an isolated temporary ChromaDB collection without impacting the production vector store.
4. **Environment Compatibility Patch**: Run `poetry run python backend/scripts/patch_environment.py` if installing on Python 3.12+ (Python 3.14).

