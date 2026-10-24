import argparse
import asyncio
import csv
import json
import logging
import math
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import settings
from app.database.database import SessionLocal
from app.repositories.clause_repository import ClauseRepository
from app.services.vector_store_service import VectorStoreService
from evaluation.metrics import evaluate_query, percentile, summarize
from evaluation.retrievers import RetrievalVariants

logger = logging.getLogger(__name__)

VARIANTS = ("dense_only", "bm25_only", "hybrid_rrf", "hybrid_reranked")
IR_METRICS = (
    "recall@5",
    "recall@10",
    "precision@5",
    "precision@10",
    "hit_rate@5",
    "mrr@10",
    "ndcg@10",
)
RAGAS_RETRIEVAL_METRICS = ("context_precision", "context_recall")


def load_dataset(path: str) -> list[dict]:
    records = []
    seen_ids = set()
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

            if record["query_id"] in seen_ids:
                raise ValueError(f"Duplicate query_id on line {line_number}: {record['query_id']}")
            seen_ids.add(record["query_id"])

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
                record["relevant_clause_ids"] = [str(c) for c in record["relevant_clause_ids"]]
                record["relevance"] = {
                    str(clause_id): 1.0
                    for clause_id in record["relevant_clause_ids"]
                }

            record["answerable"] = bool(
                record.get("answerable", bool(record["relevant_clause_ids"]))
            )
            records.append(record)

    if not records:
        raise ValueError("The evaluation dataset contains no records")
    return records


async def score_metric_with_retry(
    metric,
    kwargs: dict,
    cache: dict,
    cache_key: tuple,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> tuple[float | None, str | None]:
    if cache_key in cache:
        return cache[cache_key], None

    for attempt in range(1, max_retries + 1):
        try:
            result = await metric.ascore(**kwargs)
            value = getattr(result, "value", result)
            if value is None:
                return None, "Metric returned no value"
            score = float(value)
            if not math.isfinite(score):
                return None, f"Metric returned a non-finite value: {score}"
            cache[cache_key] = score
            return score, None
        except Exception as exc:
            err_msg = str(exc)
            is_rate_limit = "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
            if is_rate_limit and attempt < max_retries:
                # Extract suggested retry delay if present, else exponential backoff
                delay = base_delay * (2 ** (attempt - 1))
                if "retryDelay" in err_msg:
                    match = re.search(r"retryDelay['\":\s]+(\d+)", err_msg)
                    if match:
                        delay = max(delay, float(match.group(1)) + 1.0)
                logger.warning(
                    f"Rate limit encountered. Backing off for {delay:.1f}s (attempt {attempt}/{max_retries})..."
                )
                print(f" [Rate limit 429: sleeping {delay:.1f}s before retry {attempt+1}/{max_retries}]", end="", flush=True)
                await asyncio.sleep(delay)
                continue
            return None, f"{type(exc).__name__}: {exc}"
    return None, "Max retries exceeded"


def write_outputs(rows: list[dict], summary: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "retrieval_ragas_query_results.csv"
    json_path = output_dir / "retrieval_ragas_summary.json"

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)

    return csv_path, json_path


def print_comparison_table(summary: dict) -> None:
    variants = summary["variants"]
    headers = [
        "Variant",
        "MRR@10",
        "nDCG@10",
        "Recall@5",
        "HitRate@5",
        "Ctx Precision",
        "Ctx Recall",
        "Latency p50",
    ]
    col_w = [18, 10, 10, 10, 10, 15, 12, 12]

    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_w))
    separator = "-+-".join("-" * w for w in col_w)
    print("\n" + "=" * len(header_line))
    print("RETRIEVAL EVIDENCE MATRIX (RAGAS + IR METRICS)")
    print("=" * len(header_line))
    print(header_line)
    print(separator)

    for v_name, data in variants.items():
        mrr = f"{data['mrr@10']:.4f}" if data.get("mrr@10") is not None else "N/A"
        ndcg = f"{data['ndcg@10']:.4f}" if data.get("ndcg@10") is not None else "N/A"
        r5 = f"{data['recall@5']:.4f}" if data.get("recall@5") is not None else "N/A"
        hr5 = f"{data['hit_rate@5']:.4f}" if data.get("hit_rate@5") is not None else "N/A"
        cp = f"{data['context_precision']:.4f}" if data.get("context_precision") is not None else "N/A"
        cr = f"{data['context_recall']:.4f}" if data.get("context_recall") is not None else "N/A"
        lat = f"{data['latency_ms_p50']:.1f}ms" if data.get("latency_ms_p50") is not None else "N/A"

        row = [v_name, mrr, ndcg, r5, hr5, cp, cr, lat]
        print(" | ".join(val.ljust(w) for val, w in zip(row, col_w)))

    print("=" * len(header_line) + "\n")


async def run_evaluation(args: argparse.Namespace) -> None:
    records = load_dataset(args.dataset)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        records = records[: args.limit]

    judge_model = args.judge_model or "gemini-3.5-flash-lite"
    ragas_metrics = {}

    if not args.skip_ragas:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is required for Ragas evaluation. "
                "Set it in backend/.env or use --skip-ragas for IR-only evaluation."
            )
        try:
            from openai import AsyncOpenAI
            from ragas.llms import llm_factory
            from ragas.metrics.collections import ContextPrecision, ContextRecall

            openai_client = AsyncOpenAI(
                api_key=settings.GEMINI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            judge_llm = llm_factory(
                judge_model,
                provider="openai",
                client=openai_client,
                temperature=0.0,
            )
            ragas_metrics = {
                "context_precision": ContextPrecision(llm=judge_llm),
                "context_recall": ContextRecall(llm=judge_llm),
            }
        except ImportError as exc:
            raise RuntimeError(
                f"Ragas dependencies could not be loaded: {exc}. Run backend/scripts/patch_environment.py"
            ) from exc

    db = SessionLocal()
    vector_store_directory = tempfile.mkdtemp(prefix="legaldocai-retrieval-ragas-")
    vector_store = VectorStoreService(persist_directory=vector_store_directory)
    repository = ClauseRepository(db)
    variants = RetrievalVariants(vector_store)

    clauses_by_document = {}
    latencies = defaultdict(list)
    metric_values = defaultdict(lambda: defaultdict(list))
    ragas_metric_values = defaultdict(lambda: defaultdict(list))
    metric_errors = defaultdict(Counter)
    evaluation_cache = {}
    result_rows = []

    try:
        encoder = vector_store._get_encoder()
        if encoder is None:
            raise RuntimeError(
                f"Could not load embedding model '{vector_store.model_name}'."
            )
        encoder.encode(["warmup retrieval evaluation"], show_progress_bar=False)

        document_ids = list(dict.fromkeys(str(record["document_id"]) for record in records))
        for document_id in document_ids:
            clauses = repository.list_by_document_id(document_id)
            if not clauses:
                raise ValueError(f"No clauses found in DB for document_id={document_id}")
            clauses_by_document[document_id] = clauses
            count = vector_store.index_document_clauses(document_id, clauses, force=True)
            if count < 1:
                raise RuntimeError(f"No chunks indexed for document_id={document_id}")

        embedding_dimension = vector_store.validate_embedding_dimensions()
        retrieval_k = max(args.top_k, 5)

        total_runs = len(records) * len(VARIANTS)
        completed = 0

        for record in records:
            document_id = str(record["document_id"])
            clauses = clauses_by_document[document_id]
            query = record["query"]
            relevant = record["relevant_clause_ids"]
            relevance = record["relevance"]
            answerable = record["answerable"]
            ref_answer = record.get("reference_answer", "")

            for variant_name in VARIANTS:
                started = time.perf_counter()
                retrieved_results = getattr(variants, variant_name)(
                    document_id, query, clauses, retrieval_k
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                latencies[variant_name].append(elapsed_ms)

                retrieved_ids = [res.clause_id for res in retrieved_results]
                retrieved_contexts = [
                    res.text for res in retrieved_results if res.text and res.text.strip()
                ]

                # 1. Deterministic IR metrics
                ir_scores = evaluate_query(retrieved_ids, relevant, relevance)
                for metric, val in ir_scores.items():
                    if metric.startswith(("recall", "hit_rate")) and not answerable:
                        continue
                    metric_values[variant_name][metric].append(val)

                # 2. Ragas metrics
                ragas_scores = {name: None for name in RAGAS_RETRIEVAL_METRICS}
                errors = {}

                if not args.skip_ragas and answerable and ref_answer.strip():
                    if retrieved_contexts:
                        ctx_tuple = tuple(retrieved_contexts)
                        cp_key = (query, ctx_tuple, "context_precision")
                        cr_key = (query, ctx_tuple, "context_recall")
                        was_cached = cp_key in evaluation_cache

                        # Context Precision
                        cp_score, cp_err = await score_metric_with_retry(
                            ragas_metrics["context_precision"],
                            {
                                "user_input": query,
                                "reference": ref_answer,
                                "retrieved_contexts": retrieved_contexts,
                            },
                            evaluation_cache,
                            cp_key,
                            base_delay=args.request_delay,
                        )
                        if cp_err:
                            errors["context_precision"] = cp_err
                            metric_errors[variant_name]["context_precision"] += 1
                        else:
                            ragas_scores["context_precision"] = cp_score
                            ragas_metric_values[variant_name]["context_precision"].append(cp_score)

                        # Context Recall
                        cr_score, cr_err = await score_metric_with_retry(
                            ragas_metrics["context_recall"],
                            {
                                "user_input": query,
                                "reference": ref_answer,
                                "retrieved_contexts": retrieved_contexts,
                            },
                            evaluation_cache,
                            cr_key,
                            base_delay=args.request_delay,
                        )
                        if cr_err:
                            errors["context_recall"] = cr_err
                            metric_errors[variant_name]["context_recall"] += 1
                        else:
                            ragas_scores["context_recall"] = cr_score
                            ragas_metric_values[variant_name]["context_recall"].append(cr_score)

                        if not was_cached and args.request_delay > 0:
                            await asyncio.sleep(args.request_delay)
                    else:
                        ragas_scores["context_precision"] = 0.0
                        ragas_scores["context_recall"] = 0.0
                        ragas_metric_values[variant_name]["context_precision"].append(0.0)
                        ragas_metric_values[variant_name]["context_recall"].append(0.0)

                result_rows.append(
                    {
                        "query_id": record["query_id"],
                        "document_id": document_id,
                        "variant": variant_name,
                        "question": query,
                        "answerable": answerable,
                        "reference_answer": ref_answer,
                        "retrieved_clause_ids": json.dumps(retrieved_ids, ensure_ascii=False),
                        "retrieved_contexts_count": len(retrieved_contexts),
                        "latency_ms": round(elapsed_ms, 3),
                        **ir_scores,
                        **ragas_scores,
                        "metric_errors": json.dumps(errors, ensure_ascii=False),
                    }
                )

                completed += 1
                cp_display = (
                    f"cp={ragas_scores['context_precision']:.2f}"
                    if ragas_scores.get("context_precision") is not None
                    else ""
                )
                cr_display = (
                    f"cr={ragas_scores['context_recall']:.2f}"
                    if ragas_scores.get("context_recall") is not None
                    else ""
                )
                print(
                    f"[{completed}/{total_runs}] query={record['query_id']} "
                    f"variant={variant_name:<16} mrr={ir_scores['mrr@10']:.3f} "
                    f"lat={elapsed_ms:.1f}ms {cp_display} {cr_display}",
                    flush=True,
                )

    finally:
        db.close()

    output_dir = Path(args.output_dir)
    summary = {
        "dataset": str(Path(args.dataset)),
        "query_count": len(records),
        "document_count": len(clauses_by_document),
        "requested_top_k": args.top_k,
        "retrieval_k": retrieval_k,
        "embedding_model": vector_store.model_name,
        "embedding_dimension": embedding_dimension,
        "judge_model": judge_model if not args.skip_ragas else "none (skipped)",
        "isolated_vector_store_directory": vector_store_directory,
        "variants": {},
    }

    for variant_name in VARIANTS:
        variant_summary = {
            metric: summarize(metric_values[variant_name][metric])
            for metric in IR_METRICS
        }
        for ragas_m in RAGAS_RETRIEVAL_METRICS:
            variant_summary[ragas_m] = summarize(ragas_metric_values[variant_name][ragas_m])

        variant_summary["latency_ms_p50"] = percentile(latencies[variant_name], 50)
        variant_summary["latency_ms_p95"] = percentile(latencies[variant_name], 95)
        variant_summary["latency_ms_p99"] = percentile(latencies[variant_name], 99)
        variant_summary["empty_result_rate"] = (
            sum(
                1
                for row in result_rows
                if row["variant"] == variant_name
                and not json.loads(row["retrieved_clause_ids"])
            )
            / len(records)
        )
        variant_summary["metric_errors"] = dict(metric_errors[variant_name])
        summary["variants"][variant_name] = variant_summary

    csv_path, json_path = write_outputs(result_rows, summary, output_dir)
    print_comparison_table(summary)
    print(f"Query-level results: {csv_path}")
    print(f"Summary JSON: {json_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive Ragas + IR Retrieval Evaluation for LegalDocAI"
    )
    parser.add_argument(
        "--dataset",
        default=str(BACKEND_DIR / "evaluation" / "datasets" / "retrieval_gold.jsonl"),
        help="Path to evaluation dataset (JSONL)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT_DIR / "artifacts" / "retrieval-ragas-evaluation"),
        help="Directory to save query results CSV and summary JSON",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-K results to evaluate")
    parser.add_argument("--limit", type=int, help="Limit number of queries evaluated")
    parser.add_argument("--judge-model", help="Gemini judge model name (defaults to GEMINI_MODEL)")
    parser.add_argument(
        "--request-delay",
        type=float,
        default=1.5,
        help="Delay in seconds between un-cached LLM judge requests to respect API rate limits",
    )
    parser.add_argument(
        "--skip-ragas",
        action="store_true",
        help="Skip LLM-judged Ragas metrics; compute IR metrics only (fast, no API calls)",
    )
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
