import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.database import SessionLocal
from app.repositories.clause_repository import ClauseRepository
from app.services.vector_store_service import VectorStoreService
from evaluation.metrics import evaluate_query, percentile, summarize
from evaluation.retrievers import RetrievalVariants


VARIANTS = ("dense_only", "bm25_only", "hybrid_rrf", "hybrid_reranked")
METRICS = (
    "recall@5",
    "recall@10",
    "precision@5",
    "precision@10",
    "hit_rate@5",
    "mrr@10",
    "ndcg@10",
)


def load_dataset(path):
    records = []
    with Path(path).open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            required = {"query_id", "document_id", "query"}
            missing = required - record.keys()
            if missing:
                raise ValueError(f"Line {line_number} is missing fields: {sorted(missing)}")
            if "relevance" not in record and "relevant_clause_ids" not in record:
                raise ValueError(
                    f"Line {line_number} needs relevance or relevant_clause_ids"
                )
            if "relevance" in record:
                record["relevance"] = {
                    str(key): float(value)
                    for key, value in record["relevance"].items()
                    if float(value) > 0
                }
                record["relevant_clause_ids"] = list(record["relevance"])
            else:
                record["relevant_clause_ids"] = list(record["relevant_clause_ids"])
                record["relevance"] = {
                    str(clause_id): 1.0
                    for clause_id in record["relevant_clause_ids"]
                }
            records.append(record)
    if not records:
        raise ValueError("The evaluation dataset contains no records")
    return records


def write_outputs(rows, summary, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "retrieval_query_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        fields = list(rows[0]) if rows else []
        writer = csv.DictWriter(file, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)
    with (output_dir / "retrieval_summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default=str(BACKEND_DIR / "evaluation" / "datasets" / "retrieval_gold.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT_DIR / "artifacts" / "retrieval-evaluation"),
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--index-missing", action="store_true")
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    records = load_dataset(args.dataset)
    retrieval_k = max(args.top_k, 10)
    db = SessionLocal()
    vector_store = VectorStoreService()
    repository = ClauseRepository(db)
    variants = RetrievalVariants(vector_store)
    clauses_by_document = {}
    latencies = defaultdict(list)
    metric_values = defaultdict(lambda: defaultdict(list))
    query_rows = []

    try:
        document_ids = {str(record["document_id"]) for record in records}
        for document_id in document_ids:
            clauses = repository.list_by_document_id(document_id)
            if not clauses:
                raise ValueError(f"No clauses found for document_id={document_id}")
            clauses_by_document[document_id] = clauses
            if args.index_missing:
                vector_store.index_document_clauses(document_id, clauses)

        for record in records:
            document_id = str(record["document_id"])
            clauses = clauses_by_document[document_id]
            relevant = record["relevant_clause_ids"]
            relevance = record["relevance"]
            answerable = bool(record.get("answerable", bool(relevant)))
            for variant_name in VARIANTS:
                started = time.perf_counter()
                retrieved = getattr(variants, variant_name)(
                    document_id, record["query"], clauses, retrieval_k
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                retrieved_ids = [result.clause_id for result in retrieved]
                latencies[variant_name].append(elapsed_ms)
                scores = evaluate_query(retrieved_ids, relevant, relevance)
                for metric, value in scores.items():
                    if metric.startswith(("recall", "hit_rate")) and not answerable:
                        continue
                    metric_values[variant_name][metric].append(value)
                query_rows.append(
                    {
                        "query_id": record["query_id"],
                        "document_id": document_id,
                        "variant": variant_name,
                        "answerable": answerable,
                        "latency_ms": round(elapsed_ms, 3),
                        "retrieved_clause_ids": json.dumps(retrieved_ids),
                        **scores,
                    }
                )

        summary = {
            "dataset": str(Path(args.dataset)),
            "query_count": len(records),
            "document_count": len(clauses_by_document),
            "requested_top_k": args.top_k,
            "retrieval_k": retrieval_k,
            "variants": {},
        }
        for variant_name in VARIANTS:
            summary["variants"][variant_name] = {
                metric: summarize(metric_values[variant_name][metric])
                for metric in METRICS
            }
            summary["variants"][variant_name]["latency_ms_p50"] = percentile(
                latencies[variant_name], 50
            )
            summary["variants"][variant_name]["latency_ms_p95"] = percentile(
                latencies[variant_name], 95
            )
            summary["variants"][variant_name]["latency_ms_p99"] = percentile(
                latencies[variant_name], 99
            )
            summary["variants"][variant_name]["empty_result_rate"] = (
                sum(
                    1
                    for row in query_rows
                    if row["variant"] == variant_name
                    and not json.loads(row["retrieved_clause_ids"])
                )
                / len(records)
            )
        output_dir = Path(args.output_dir)
        write_outputs(query_rows, summary, output_dir)
        print(json.dumps(summary, indent=2))
        print(f"Query-level results: {output_dir / 'retrieval_query_results.csv'}")
        print(f"Summary: {output_dir / 'retrieval_summary.json'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
