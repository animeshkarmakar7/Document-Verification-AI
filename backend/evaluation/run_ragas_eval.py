import argparse
import asyncio
import csv
import json
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
from app.services.rag_service import RAGService
from app.services.vector_store_service import VectorStoreService
from evaluation.metrics import percentile, summarize


RAGAS_METRICS = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_correctness",
    "answer_relevancy",
)
ABSTENTION_PATTERN = re.compile(
    r"\b(?:cannot answer|can't answer|unable to answer|cannot determine|"
    r"unable to determine|not enough information|does not specify|do not specify|"
    r"not stated|not provided|not available in (?:the )?(?:document|context|clauses)|"
    r"not contain|no information|consult a legal professional)\b",
    re.IGNORECASE,
)


def load_dataset(path):
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

            required = {
                "query_id",
                "document_id",
                "query",
                "relevant_clause_ids",
                "answerable",
                "reference_answer",
            }
            missing = required - record.keys()
            if missing:
                raise ValueError(
                    f"Dataset line {line_number} is missing fields: {sorted(missing)}"
                )
            if record["query_id"] in seen_ids:
                raise ValueError(f"Duplicate query_id: {record['query_id']}")
            if not isinstance(record["relevant_clause_ids"], list):
                raise ValueError(
                    f"relevant_clause_ids must be a list on line {line_number}"
                )
            if not isinstance(record["answerable"], bool):
                raise ValueError(f"answerable must be boolean on line {line_number}")
            if not str(record["query"]).strip() or not str(record["reference_answer"]).strip():
                raise ValueError(
                    f"query and reference_answer must be non-empty on line {line_number}"
                )
            if record["answerable"] and not record["relevant_clause_ids"]:
                raise ValueError(
                    f"Answerable query {record['query_id']} needs relevant_clause_ids"
                )
            if not record["answerable"] and record["relevant_clause_ids"]:
                raise ValueError(
                    f"Unanswerable query {record['query_id']} must have no relevant_clause_ids"
                )
            record["relevant_clause_ids"] = [
                str(value) for value in record["relevant_clause_ids"]
            ]
            records.append(record)
            seen_ids.add(record["query_id"])

    if not records:
        raise ValueError("The evaluation dataset contains no records")
    return records


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def citation_metrics(citations, expected_clause_ids, clauses):
    expected = set(expected_clause_ids)
    cited_ids = [
        str(item.get("clause_id", ""))
        for item in citations
        if item.get("clause_id")
    ]
    cited = set(cited_ids)
    correct = cited & expected

    if expected:
        precision = len(correct) / len(cited) if cited else 0.0
        recall = len(correct) / len(expected)
    else:
        precision = 1.0 if not cited else 0.0
        recall = None

    clause_text_by_id = {str(clause.clause_id): clause.text or "" for clause in clauses}
    quote_matches = 0
    quote_total = 0
    for citation in citations:
        clause_id = str(citation.get("clause_id", ""))
        quote = normalize_text(citation.get("quoted_text", ""))
        source = normalize_text(clause_text_by_id.get(clause_id, ""))
        if not quote:
            continue
        quote_total += 1
        if quote in source:
            quote_matches += 1

    return {
        "citation_precision": precision,
        "citation_recall": recall,
        "citation_quote_match_rate": (
            quote_matches / quote_total if quote_total else None
        ),
        "cited_clause_ids": cited_ids,
    }


def abstention_prediction(answer, confidence):
    if confidence is not None:
        try:
            if float(confidence) < 0.5:
                return True
        except (TypeError, ValueError):
            pass
    return bool(ABSTENTION_PATTERN.search(str(answer or "")))


async def score_metric(metric, kwargs):
    try:
        result = await metric.ascore(**kwargs)
        value = getattr(result, "value", result)
        if value is None:
            return None, "Metric returned no value"
        score = float(value)
        if not math.isfinite(score):
            return None, f"Metric returned a non-finite value: {score}"
        return score, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def write_outputs(rows, summary, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "ragas_query_results.csv"
    json_path = output_dir / "ragas_summary.json"

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)

    return csv_path, json_path


async def run_evaluation(args):
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is required for Ragas judging and the configured LegalDocAI chatbot. "
            "Set it in backend/.env or the environment."
        )

    try:
        from google import genai
        from openai import AsyncOpenAI
        from ragas.embeddings import GoogleEmbeddings
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerCorrectness,
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Ragas dependencies are missing. Run poetry lock and poetry install --with dev."
        ) from exc

    records = load_dataset(args.dataset)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        records = records[: args.limit]

    judge_model = args.judge_model or settings.GEMINI_MODEL
    embedding_model = args.embedding_model

    google_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    openai_compatible_client = AsyncOpenAI(
        api_key=settings.GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    judge_llm = llm_factory(
        judge_model,
        provider="openai",
        client=openai_compatible_client,
        temperature=0.0,
    )
    judge_embeddings = GoogleEmbeddings(
        client=google_client,
        model=embedding_model,
    )

    metrics = {
        "context_precision": ContextPrecision(llm=judge_llm),
        "context_recall": ContextRecall(llm=judge_llm),
        "faithfulness": Faithfulness(llm=judge_llm),
        "answer_correctness": AnswerCorrectness(
            llm=judge_llm,
            embeddings=judge_embeddings,
        ),
        "answer_relevancy": AnswerRelevancy(
            llm=judge_llm,
            embeddings=judge_embeddings,
        ),
    }

    db = SessionLocal()
    vector_store_directory = tempfile.mkdtemp(prefix="legaldocai-ragas-")
    vector_store = VectorStoreService(persist_directory=vector_store_directory)
    clause_repository = ClauseRepository(db)
    clauses_by_document = {}
    indexed_chunk_counts = {}
    result_rows = []
    metric_values = defaultdict(list)
    metric_errors = Counter()
    generation_modes = Counter()
    latency_values = []
    embedding_dimension = None

    try:
        encoder = vector_store._get_encoder()
        if encoder is None:
            raise RuntimeError(
                f"Could not load embedding model '{vector_store.model_name}'."
            )
        encoder.encode(["LegalDocAI Ragas evaluation warmup"], show_progress_bar=False)

        document_ids = list(
            dict.fromkeys(str(record["document_id"]) for record in records)
        )
        for document_id in document_ids:
            clauses = clause_repository.list_by_document_id(document_id)
            if not clauses:
                raise ValueError(f"No clauses found for document_id={document_id}")
            clauses_by_document[document_id] = clauses
            count = vector_store.index_document_clauses(
                document_id,
                clauses,
                force=True,
            )
            if count < 1:
                raise RuntimeError(f"No chunks were indexed for document_id={document_id}")
            indexed_chunk_counts[document_id] = count

        embedding_dimension = vector_store.validate_embedding_dimensions()
        rag_service = RAGService(
            db=db,
            api_key=settings.GEMINI_API_KEY,
            model_name=settings.GEMINI_MODEL,
            vector_store=vector_store,
        )
        if rag_service.client is None:
            raise RuntimeError("LegalDocAI could not initialize its configured Gemini client.")

        for index, record in enumerate(records, start=1):
            document_id = str(record["document_id"])
            clauses = clauses_by_document[document_id]
            started = time.perf_counter()
            chatbot_result = rag_service.chat(
                document_id=document_id,
                query=record["query"],
                top_k=args.top_k,
                persist_messages=False,
                include_evaluation_details=True,
                index_document=False,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            latency_values.append(latency_ms)

            answer = str(chatbot_result.get("answer") or "")
            contexts = [
                str(item)
                for item in chatbot_result.get("retrieved_contexts", [])
                if str(item).strip()
            ]
            retrieved_ids = [
                str(item)
                for item in chatbot_result.get("retrieved_clause_ids", [])
            ]
            citations = chatbot_result.get("citations") or []
            expected_ids = record["relevant_clause_ids"]
            scores = {name: None for name in RAGAS_METRICS}
            errors = {}

            if contexts and answer.strip():
                scores["faithfulness"], error = await score_metric(
                    metrics["faithfulness"],
                    {
                        "user_input": record["query"],
                        "response": answer,
                        "retrieved_contexts": contexts,
                    },
                )
                if error:
                    errors["faithfulness"] = error
                    metric_errors["faithfulness"] += 1
            else:
                errors["faithfulness"] = "Skipped because answer or retrieved context is empty"

            if record["answerable"]:
                if contexts:
                    for name in ("context_precision", "context_recall"):
                        scores[name], error = await score_metric(
                            metrics[name],
                            {
                                "user_input": record["query"],
                                "reference": record["reference_answer"],
                                "retrieved_contexts": contexts,
                            },
                        )
                        if error:
                            errors[name] = error
                            metric_errors[name] += 1
                else:
                    scores["context_precision"] = 0.0
                    scores["context_recall"] = 0.0

            for name in ("answer_correctness", "answer_relevancy"):
                metric_args = {
                    "user_input": record["query"],
                    "response": answer,
                }
                if name == "answer_correctness":
                    metric_args["reference"] = record["reference_answer"]
                scores[name], error = await score_metric(metrics[name], metric_args)
                if error:
                    errors[name] = error
                    metric_errors[name] += 1

            citation_results = citation_metrics(citations, expected_ids, clauses)
            predicted_abstention = abstention_prediction(
                answer,
                chatbot_result.get("confidence"),
            )
            abstention_accuracy = float(
                predicted_abstention == (not record["answerable"])
            )
            generation_mode = str(chatbot_result.get("generation_mode", "unknown"))
            generation_modes[generation_mode] += 1

            for name, value in scores.items():
                if value is not None:
                    metric_values[name].append(value)

            result_rows.append(
                {
                    "query_id": record["query_id"],
                    "split": record.get("split", ""),
                    "category": record.get("category", ""),
                    "document_id": document_id,
                    "question": record["query"],
                    "answerable": record["answerable"],
                    "reference_answer": record["reference_answer"],
                    "generated_answer": answer,
                    "confidence": chatbot_result.get("confidence"),
                    "generation_mode": generation_mode,
                    "retrieved_clause_ids": json.dumps(retrieved_ids, ensure_ascii=False),
                    "retrieved_contexts": json.dumps(contexts, ensure_ascii=False),
                    "citations": json.dumps(citations, ensure_ascii=False),
                    "latency_ms": round(latency_ms, 3),
                    "predicted_abstention": predicted_abstention,
                    "abstention_accuracy": abstention_accuracy,
                    "citation_precision": citation_results["citation_precision"],
                    "citation_recall": citation_results["citation_recall"],
                    "citation_quote_match_rate": citation_results["citation_quote_match_rate"],
                    **scores,
                    "metric_errors": json.dumps(errors, ensure_ascii=False),
                }
            )

            print(
                f"[{index}/{len(records)}] {record['query_id']} "
                f"mode={generation_mode} latency_ms={latency_ms:.1f}"
            )

    finally:
        db.close()

    output_dir = Path(args.output_dir)
    summary = {
        "dataset": str(Path(args.dataset)),
        "query_count": len(records),
        "document_count": len(clauses_by_document),
        "top_k": args.top_k,
        "chat_model": settings.GEMINI_MODEL,
        "judge_model": judge_model,
        "judge_embedding_model": embedding_model,
        "ragas_version_range": ">=0.4.3,<0.5.0",
        "application_embedding_model": settings.EMBEDDING_MODEL,
        "application_embedding_dimension": embedding_dimension,
        "isolated_vector_store_directory": vector_store_directory,
        "indexed_chunk_counts": indexed_chunk_counts,
        "generation_modes": dict(generation_modes),
        "metric_error_counts": dict(metric_errors),
        "metrics": {
            name: {
                "mean": summarize(metric_values[name]),
                "scored_queries": len(metric_values[name]),
            }
            for name in RAGAS_METRICS
        },
        "custom_metrics": {
            name: {
                "mean": summarize([row[name] for row in result_rows]),
                "scored_queries": sum(row[name] is not None for row in result_rows),
            }
            for name in (
                "citation_precision",
                "citation_recall",
                "citation_quote_match_rate",
                "abstention_accuracy",
            )
        },
        "chat_latency_ms": {
            "p50": percentile(latency_values, 50),
            "p95": percentile(latency_values, 95),
            "p99": percentile(latency_values, 99),
        },
    }
    csv_path, json_path = write_outputs(result_rows, summary, output_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Query-level results: {csv_path}")
    print(f"Summary: {json_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default=str(
            BACKEND_DIR / "evaluation" / "datasets" / "retrieval_gold.jsonl"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT_DIR / "artifacts" / "ragas-evaluation"),
    )
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--judge-model")
    parser.add_argument("--embedding-model", default="gemini-embedding-001")
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")
    asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
