from unittest.mock import MagicMock

from app.models.clause import Clause
from app.services.rag_service import GroundedAnswerBatch, GroundedCitation, RAGService
from app.services.vector_store_service import VectorSearchResult


def test_rag_chat_evaluation_mode_returns_context_without_persisting_messages():
    db = MagicMock()
    vector_store = MagicMock()
    vector_store.hybrid_search.return_value = [
        VectorSearchResult(
            clause_id="doc-1-clause-0001",
            text="The Tenant shall pay a refundable security deposit of INR 96,000.",
            score=0.03,
            source_start=0,
            source_end=63,
            heading="Security Deposit",
        )
    ]
    router = MagicMock()
    router.gemini_client = MagicMock()
    router.generate_structured.return_value = GroundedAnswerBatch(
        answer="The security deposit is INR 96,000.",
        confidence=0.9,
        citations=[
            GroundedCitation(
                clause_id="doc-1-clause-0001",
                source_span_start=0,
                source_span_end=63,
                quoted_text="The Tenant shall pay a refundable security deposit of INR 96,000.",
            )
        ],
    )

    service = RAGService(
        db=db,
        api_key="test-key",
        vector_store=vector_store,
        router=router,
    )
    service.doc_repo.get_by_id.return_value = object()
    service.clause_repo.list_by_document.return_value = [
        Clause(
            id="clause-pk-1",
            document_id="doc-1",
            clause_id="doc-1-clause-0001",
            text="The Tenant shall pay a refundable security deposit of INR 96,000.",
            source_start=0,
            source_end=63,
            order_index=0,
        )
    ]

    result = service.chat(
        document_id="doc-1",
        query="How much is the security deposit?",
        persist_messages=False,
        include_evaluation_details=True,
        index_document=False,
    )

    assert result["answer"] == "The security deposit is INR 96,000."
    assert result["retrieved_clause_ids"] == ["doc-1-clause-0001"]
    assert result["retrieved_contexts"] == [
        "The Tenant shall pay a refundable security deposit of INR 96,000."
    ]
    assert result["generation_mode"] == "llm_router"
    service.chat_repo.create.assert_not_called()
    db.commit.assert_not_called()
    vector_store.index_document_clauses.assert_not_called()
