from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.clause import Clause
from app.config.settings import settings
from app.services.vector_store_service import VectorSearchResult, VectorStoreService


def make_clause(clause_id, text, order_index):
    return Clause(
        id=f"pk-{clause_id}",
        document_id="doc-1",
        clause_id=clause_id,
        text=text,
        source_start=order_index * 100,
        source_end=order_index * 100 + len(text),
        order_index=order_index,
    )


def test_bm25_returns_only_positive_matching_chunks():
    service = object.__new__(VectorStoreService)
    service.text_splitter = None
    clauses = [
        make_clause(
            "doc-1-clause-0001",
            "The tenant shall pay a refundable security deposit.",
            0,
        ),
        make_clause(
            "doc-1-clause-0002",
            "Either party may terminate the agreement with written notice.",
            1,
        ),
    ]

    results = service._sparse_keyword_search(
        "security deposit",
        clauses,
        top_k=20,
    )

    assert len(results) == 1
    assert results[0].clause_id == "doc-1-clause-0001"
    assert results[0].chunk_id
    assert results[0].score > 0


def test_dense_search_fails_when_configured_encoder_is_unavailable():
    service = object.__new__(VectorStoreService)
    service.collection = MagicMock()
    service.model_name = "BAAI/bge-large-en-v1.5"
    service._get_encoder = MagicMock(return_value=None)

    with pytest.raises(RuntimeError, match="Could not load embedding model"):
        service.dense_search(
            document_id="doc-1",
            query="What is the security deposit?",
            candidate_k=20,
        )

    service.collection.query.assert_not_called()


def test_extracted_chunk_indexing_fails_without_chromadb():
    service = object.__new__(VectorStoreService)
    service.collection = None
    service.extracted_collection = None
    service.dedup_cache = MagicMock()
    service.dedup_cache.seen_or_mark.return_value = False
    chunk = SimpleNamespace(
        chunk_id="chunk-1",
        chunk_hash="hash-1",
        text="A legal clause.",
        metadata={"document_id": "doc-1"},
    )

    with pytest.raises(RuntimeError, match="ChromaDB collection is not initialized"):
        service.index_extracted_chunks([chunk])


def test_blank_query_is_rejected_by_hybrid_search():
    service = object.__new__(VectorStoreService)

    with pytest.raises(ValueError, match="query must not be empty"):
        service.hybrid_search_with_trace(
            document_id="doc-1",
            query="  ",
            clauses=[],
            top_k=5,
            candidate_k=20,
        )



def test_hybrid_pipeline_requests_twenty_candidates_and_reranks_to_five():
    service = object.__new__(VectorStoreService)
    dense_result = VectorSearchResult(
        clause_id="doc-1-clause-0001",
        chunk_id="chunk-1",
        text="The refundable deposit is INR 96,000.",
        score=0.8,
        source_start=0,
        source_end=37,
    )
    sparse_result = VectorSearchResult(
        clause_id="doc-1-clause-0001",
        chunk_id="chunk-1",
        text="The refundable deposit is INR 96,000.",
        score=2.4,
        source_start=0,
        source_end=37,
    )
    fused_result = VectorSearchResult(
        clause_id="doc-1-clause-0001",
        chunk_id="chunk-1",
        text="The refundable deposit is INR 96,000.",
        score=0.03,
        rrf_score=0.03,
        source_start=0,
        source_end=37,
    )
    final_result = VectorSearchResult(
        clause_id="doc-1-clause-0001",
        chunk_id="chunk-1",
        text="The refundable deposit is INR 96,000.",
        score=2.8,
        rrf_score=0.03,
        rerank_score=2.8,
        source_start=0,
        source_end=37,
    )
    service.dense_search = MagicMock(return_value=[dense_result])
    service.sparse_search = MagicMock(return_value=[sparse_result])
    service._rrf_fuse = MagicMock(return_value=[fused_result])
    service.reranker = MagicMock()
    service.reranker.model_name = settings.RERANKER_MODEL
    service.reranker.rerank.return_value = [final_result]

    results, trace = service.hybrid_search_with_trace(
        document_id="doc-1",
        query="What is the refundable deposit?",
        clauses=[make_clause("doc-1-clause-0001", "The refundable deposit is INR 96,000.", 0)],
        top_k=5,
        candidate_k=20,
    )

    service.dense_search.assert_called_once_with(
        "doc-1",
        "What is the refundable deposit?",
        20,
    )
    service.sparse_search.assert_called_once()
    service._rrf_fuse.assert_called_once_with(
        [dense_result],
        [sparse_result],
        top_k=20,
        k=settings.RRF_K,
    )
    service.reranker.rerank.assert_called_once_with(
        "What is the refundable deposit?",
        [fused_result],
        top_k=5,
    )
    assert results == [final_result]
    assert trace["dense_candidate_count"] == 1
    assert trace["sparse_candidate_count"] == 1
    assert trace["fused_candidate_count"] == 1
    assert trace["final_k"] == 5
    assert trace["reranker_applied"] is True



def test_chunk_spans_map_back_to_exact_clause_source_text():
    service = object.__new__(VectorStoreService)
    service.text_splitter = None
    text = (
        "Section 1\n\nThe tenant shall pay a refundable deposit.\n\n"
        "Section 2\n\nThe tenant must provide thirty days notice."
    )
    clause = make_clause("doc-1-clause-0001", text, 1)

    chunks = service.chunk_clause(clause)

    assert len(chunks) == 2
    for chunk in chunks:
        relative_start = chunk.source_start - clause.source_start
        relative_end = chunk.source_end - clause.source_start
        assert clause.text[relative_start:relative_end] == chunk.text



def test_page_extraction_chunks_are_stored_outside_clause_retrieval_collection():
    service = object.__new__(VectorStoreService)
    service.collection = MagicMock()
    service.extracted_collection = MagicMock()
    service._get_encoder = MagicMock(
        return_value=SimpleNamespace(
            encode=lambda texts, show_progress_bar: [[0.1, 0.2] for _ in texts],
            get_embedding_dimension=lambda: 2,
        )
    )
    chunk = SimpleNamespace(
        chunk_id="doc-1-p00001-s0001-c001-hash",
        chunk_hash="hash",
        text="Extracted page text without a clause ID.",
        metadata={
            "document_id": "doc-1",
            "chunk_id": "doc-1-p00001-s0001-c001-hash",
        },
    )
    service.extracted_collection.get.return_value = {"ids": []}

    indexed = service.index_extracted_chunks([chunk])

    assert indexed == 1
    service.extracted_collection.upsert.assert_called_once()
    service.collection.upsert.assert_not_called()
