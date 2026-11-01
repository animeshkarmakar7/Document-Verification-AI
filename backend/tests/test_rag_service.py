from unittest.mock import MagicMock

import pytest

from app.models.clause import Clause
from app.services.rag_service import DocumentNotFoundError, RAGService
from app.services.vector_store_service import VectorSearchResult


@pytest.fixture
def mock_db():
    return MagicMock()


def test_rag_service_doc_not_found(mock_db):
    service = RAGService(db=mock_db, client=MagicMock())
    service.doc_repo.get_by_id = MagicMock(return_value=None)

    with pytest.raises(DocumentNotFoundError):
        service.chat("bad-doc", "What is the deposit?")


def test_rag_service_uses_gemini_and_validates_citations(mock_db):
    vector_store = MagicMock()
    vector_store.hybrid_search_with_trace.return_value = (
        [
            VectorSearchResult(
                clause_id="doc-1-clause-0001",
                chunk_id="doc-1-clause-0001-chunk-001",
                text="The tenant shall pay a security deposit of $1,000.",
                score=2.1,
                source_start=0,
                source_end=50,
            )
        ],
        {"retrieval_pipeline": "dense_bm25_rrf_cross_encoder"},
    )
    client = MagicMock()
    client.models.generate_content.return_value.text = (
        '{"answer": "The deposit is $1,000.", "confidence": 0.95, '
        '"citations": [{"clause_id": "doc-1-clause-0001", '
        '"source_span_start": 23, "source_span_end": 49, '
        '"quoted_text": "security deposit of $1,000"}]}'
    )
    service = RAGService(
        db=mock_db,
        api_key="mock_key",
        vector_store=vector_store,
        client=client,
    )
    service.doc_repo.get_by_id.return_value = object()
    service.clause_repo.list_by_document.return_value = [
        Clause(
            id="clause-pk-1",
            document_id="doc-1",
            clause_id="doc-1-clause-0001",
            text="The tenant shall pay a security deposit of $1,000.",
            source_start=0,
            source_end=50,
            order_index=0,
        )
    ]

    result = service.chat(
        "doc-1",
        "How much is the deposit?",
        persist_messages=False,
        index_document=False,
        include_evaluation_details=True,
    )

    assert result["answer"] == "The deposit is $1,000."
    assert result["confidence"] == 0.95
    assert result["generation_mode"] == "gemini"
    assert result["retrieved_chunk_ids"] == ["doc-1-clause-0001-chunk-001"]
    assert result["retrieval_trace"]["retrieval_pipeline"] == "dense_bm25_rrf_cross_encoder"
    client.models.generate_content.assert_called_once()


def test_rag_service_does_not_invent_context_when_retrieval_is_empty(mock_db):
    vector_store = MagicMock()
    vector_store.hybrid_search_with_trace.return_value = (
        [],
        {"retrieval_pipeline": "dense_bm25_rrf_cross_encoder"},
    )
    service = RAGService(
        db=mock_db,
        api_key="",
        vector_store=vector_store,
        client=None,
    )
    service.doc_repo.get_by_id.return_value = object()
    service.clause_repo.list_by_document.return_value = [
        Clause(
            id="clause-pk-2",
            document_id="doc-2",
            clause_id="doc-2-clause-0001",
            text="The weather in California is warm.",
            source_start=0,
            source_end=34,
            order_index=0,
        )
    ]

    result = service.chat(
        "doc-2",
        "What is the tenant's passport number?",
        persist_messages=False,
        index_document=False,
        include_evaluation_details=True,
    )

    assert result["confidence"] == 0.0
    assert result["citations"] == []
    assert result["generation_mode"] == "no_retrieved_context"
    assert result["retrieved_contexts"] == []


def test_rag_service_propagates_gemini_errors_without_fallback(mock_db):
    vector_store = MagicMock()
    vector_store.hybrid_search_with_trace.return_value = (
        [
            VectorSearchResult(
                clause_id="doc-1-clause-0001",
                chunk_id="chunk-1",
                text="The tenant shall pay a security deposit of $1,000.",
                score=2.1,
                source_start=0,
                source_end=50,
            )
        ],
        {"retrieval_pipeline": "dense_bm25_rrf_cross_encoder"},
    )
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("Gemini unavailable")
    service = RAGService(
        db=mock_db,
        api_key="mock_key",
        vector_store=vector_store,
        client=client,
    )
    service.doc_repo.get_by_id.return_value = object()
    service.clause_repo.list_by_document.return_value = [
        Clause(
            id="clause-pk-1",
            document_id="doc-1",
            clause_id="doc-1-clause-0001",
            text="The tenant shall pay a security deposit of $1,000.",
            source_start=0,
            source_end=50,
            order_index=0,
        )
    ]

    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        service.chat(
            "doc-1",
            "How much is the deposit?",
            persist_messages=False,
            index_document=False,
        )
