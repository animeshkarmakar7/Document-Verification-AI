from unittest.mock import MagicMock

import pytest

from app.models.clause import Clause
from app.services import rag_service as rag_service_module
from app.services.rag_service import GeneratedCitation, RAGService
from app.services.vector_store_service import VectorSearchResult


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture(autouse=True)
def disable_gemini_pacing(monkeypatch):
    monkeypatch.setattr(
        rag_service_module,
        "wait_for_gemini_request",
        lambda: None,
    )


def configure_service_repositories(service, clauses):
    service.doc_repo.get_by_id = MagicMock(return_value=object())
    service.clause_repo.list_by_document = MagicMock(return_value=clauses)


def test_rag_service_doc_not_found(mock_db):
    service = RAGService(db=mock_db, client=MagicMock())
    service.doc_repo.get_by_id = MagicMock(return_value=None)

    with pytest.raises(rag_service_module.DocumentNotFoundError):
        service.chat("bad-doc", "What is the deposit?")


def test_rag_service_grounds_citations_from_exact_retrieved_text(mock_db):
    source_text = "The tenant shall pay a security deposit of $1,000."
    source_start = 100
    source_end = source_start + len(source_text)
    quote = "security deposit of $1,000"
    vector_store = MagicMock()
    vector_store.hybrid_search_with_trace.return_value = (
        [
            VectorSearchResult(
                clause_id="doc-1-clause-0001",
                chunk_id="doc-1-clause-0001-chunk-001",
                text=source_text,
                score=2.1,
                source_start=source_start,
                source_end=source_end,
            )
        ],
        {"retrieval_pipeline": "dense_bm25_rrf_cross_encoder"},
    )
    client = MagicMock()
    client.models.generate_content.return_value.text = (
        '{"answer": "The deposit is $1,000.", "confidence": 0.95, '
        '"citations": [{"clause_id": "doc-1-clause-0001", '
        '"quoted_text": "security   deposit of $1,000"}]}'
    )
    service = RAGService(
        db=mock_db,
        api_key="mock_key",
        vector_store=vector_store,
        client=client,
    )
    configure_service_repositories(
        service,
        [
            Clause(
                id="clause-pk-1",
                document_id="doc-1",
                clause_id="doc-1-clause-0001",
                text=source_text,
                source_start=source_start,
                source_end=source_end,
                order_index=0,
            )
        ],
    )

    result = service.chat(
        "doc-1",
        "How much is the deposit?",
        persist_messages=False,
        index_document=False,
        include_evaluation_details=True,
    )

    expected_start = source_start + source_text.index(quote)
    expected_end = expected_start + len(quote)

    assert result["answer"] == "The deposit is $1,000."
    assert result["confidence"] == 0.95
    assert result["generation_mode"] == "gemini"
    assert result["retrieved_chunk_ids"] == ["doc-1-clause-0001-chunk-001"]
    assert result["retrieval_trace"]["retrieval_pipeline"] == "dense_bm25_rrf_cross_encoder"
    assert result["citations"] == [
        {
            "clause_id": "doc-1-clause-0001",
            "source_span_start": expected_start,
            "source_span_end": expected_end,
            "quoted_text": quote,
        }
    ]
    client.models.generate_content.assert_called_once()


def test_grounded_quote_span_maps_collapsed_whitespace_to_source_offsets():
    source = "Section A:\n   The tenant shall pay on time."
    quote = "The tenant   shall\npay"

    start, end = RAGService._find_quote_span(source, quote)

    assert source[start:end] == "The tenant shall pay"


def test_rag_service_rejects_quotes_not_present_in_retrieved_evidence():
    source_text = "The tenant shall pay a security deposit of $1,000."
    source_start = 20
    results = [
        VectorSearchResult(
            clause_id="doc-1-clause-0001",
            chunk_id="chunk-1",
            text=source_text,
            score=1.0,
            source_start=source_start,
            source_end=source_start + len(source_text),
        )
    ]

    with pytest.raises(ValueError, match="was not found verbatim"):
        RAGService._ground_citations(
            [
                GeneratedCitation(
                    clause_id="doc-1-clause-0001",
                    quoted_text="The landlord must refund $10,000.",
                )
            ],
            results,
        )


def test_rag_service_rejects_citations_to_unretrieved_clauses():
    source_text = "The tenant shall pay a security deposit."
    results = [
        VectorSearchResult(
            clause_id="doc-1-clause-0001",
            chunk_id="chunk-1",
            text=source_text,
            score=1.0,
            source_start=0,
            source_end=len(source_text),
        )
    ]

    with pytest.raises(ValueError, match="was not found verbatim"):
        RAGService._ground_citations(
            [
                GeneratedCitation(
                    clause_id="doc-1-clause-9999",
                    quoted_text=source_text,
                )
            ],
            results,
        )


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
    configure_service_repositories(
        service,
        [
            Clause(
                id="clause-pk-2",
                document_id="doc-2",
                clause_id="doc-2-clause-0001",
                text="The weather in California is warm.",
                source_start=0,
                source_end=len("The weather in California is warm."),
                order_index=0,
            )
        ],
    )

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
    source_text = "The tenant shall pay a security deposit of $1,000."
    vector_store = MagicMock()
    vector_store.hybrid_search_with_trace.return_value = (
        [
            VectorSearchResult(
                clause_id="doc-1-clause-0001",
                chunk_id="chunk-1",
                text=source_text,
                score=2.1,
                source_start=0,
                source_end=len(source_text),
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
    configure_service_repositories(
        service,
        [
            Clause(
                id="clause-pk-1",
                document_id="doc-1",
                clause_id="doc-1-clause-0001",
                text=source_text,
                source_start=0,
                source_end=len(source_text),
                order_index=0,
            )
        ],
    )

    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        service.chat(
            "doc-1",
            "How much is the deposit?",
            persist_messages=False,
            index_document=False,
        )
