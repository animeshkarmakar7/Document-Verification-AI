from unittest.mock import MagicMock

import pytest

from app.models.clause import Clause
from app.services import rag_service as rag_service_module
from app.services.rag_service import RAGService
from app.services.vector_store_service import VectorSearchResult


@pytest.fixture(autouse=True)
def disable_gemini_pacing(monkeypatch):
    monkeypatch.setattr(
        rag_service_module,
        "wait_for_gemini_request",
        lambda: None,
    )


def test_rag_chat_evaluation_mode_returns_context_without_persisting_messages():
    db = MagicMock()
    source_text = "The Tenant shall pay a refundable security deposit of INR 96,000."
    source_end = len(source_text)
    vector_store = MagicMock()
    vector_store.hybrid_search_with_trace.return_value = (
        [
            VectorSearchResult(
                clause_id="doc-1-clause-0001",
                chunk_id="doc-1-clause-0001-chunk-001",
                text=source_text,
                score=2.1,
                source_start=0,
                source_end=source_end,
                heading="Security Deposit",
            )
        ],
        {
            "retrieval_pipeline": "dense_bm25_rrf_cross_encoder",
            "dense_candidate_count": 20,
            "sparse_candidate_count": 20,
            "fused_candidate_count": 20,
        },
    )
    client = MagicMock()
    client.models.generate_content.return_value.text = (
        '{"answer": "The security deposit is INR 96,000.", "confidence": 0.9, '
        '"citations": [{"clause_id": "doc-1-clause-0001", '
        '"quoted_text": "The Tenant shall pay a refundable security deposit of INR 96,000."}]}'
    )

    service = RAGService(
        db=db,
        api_key="test-key",
        vector_store=vector_store,
        client=client,
    )
    service.doc_repo.get_by_id = MagicMock(return_value=object())
    service.chat_repo.create = MagicMock()
    service.clause_repo.list_by_document = MagicMock(
        return_value=[
            Clause(
                id="clause-pk-1",
                document_id="doc-1",
                clause_id="doc-1-clause-0001",
                text=source_text,
                source_start=0,
                source_end=source_end,
                order_index=0,
            )
        ]
    )

    result = service.chat(
        document_id="doc-1",
        query="How much is the security deposit?",
        persist_messages=False,
        include_evaluation_details=True,
        index_document=False,
    )

    assert result["answer"] == "The security deposit is INR 96,000."
    assert result["retrieved_clause_ids"] == ["doc-1-clause-0001"]
    assert result["retrieved_chunk_ids"] == ["doc-1-clause-0001-chunk-001"]
    assert result["retrieved_contexts"] == [source_text]
    assert result["generation_mode"] == "gemini"
    assert result["retrieval_trace"]["retrieval_pipeline"] == "dense_bm25_rrf_cross_encoder"
    assert result["citations"] == [
        {
            "clause_id": "doc-1-clause-0001",
            "source_span_start": 0,
            "source_span_end": source_end,
            "quoted_text": source_text,
        }
    ]
    service.chat_repo.create.assert_not_called()
    db.commit.assert_not_called()
    vector_store.index_document_clauses.assert_not_called()
