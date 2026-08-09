from datetime import UTC, datetime
from unittest.mock import MagicMock
import pytest

from app.models.clause import Clause
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.services.rag_service import (
    DocumentNotFoundError,
    GroundedAnswerBatch,
    GroundedCitation,
    RAGService,
)


@pytest.fixture
def mock_db():
    return MagicMock()


def test_rag_service_doc_not_found(mock_db):
    service = RAGService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=None)
    with pytest.raises(DocumentNotFoundError):
        service.chat("bad-doc", "What is the deposit?")


def test_rag_service_success(mock_db):
    doc = Document(
        id="doc-1",
        original_filename="doc.pdf",
        stored_filename="stored.pdf",
        mime_type="application/pdf",
        extension="pdf",
        storage_uri="/tmp/doc.pdf",
        object_key="doc-1.pdf",
        file_size=1024,
        sha256="abc123",
        status=DocumentStatus.EXPLAINED,
    )
    clause = Clause(
        id="clause-pk-1",
        document_id="doc-1",
        clause_id="doc-1-clause-0001",
        text="The tenant shall pay a security deposit of $1,000.",
        source_start=0,
        source_end=50,
        order_index=0,
    )

    service = RAGService(db=mock_db, api_key="mock_key")
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    service.clause_repo.list_by_document = MagicMock(return_value=[clause])
    service.client = MagicMock()

    mock_response = MagicMock()
    mock_response.text = '{"answer": "The deposit is $1,000.", "confidence": 0.95, "citations": [{"clause_id": "doc-1-clause-0001", "source_span_start": 0, "source_span_end": 50, "quoted_text": "security deposit of $1,000"}]}'
    service.client.models.generate_content.return_value = mock_response

    res = service.chat("doc-1", "How much is the deposit?")
    assert res["answer"] == "The deposit is $1,000."
    assert res["confidence"] == 0.95
    assert len(res["citations"]) == 1
    assert res["citations"][0]["clause_id"] == "doc-1-clause-0001"


def test_rag_service_fallback_disclaimer(mock_db):
    doc = Document(
        id="doc-2",
        original_filename="doc.pdf",
        stored_filename="stored.pdf",
        mime_type="application/pdf",
        extension="pdf",
        storage_uri="/tmp/doc.pdf",
        object_key="doc-2.pdf",
        file_size=1024,
        sha256="xyz789",
        status=DocumentStatus.EXPLAINED,
    )
    clause = Clause(
        id="clause-pk-2",
        document_id="doc-2",
        clause_id="doc-2-clause-0001",
        text="The weather in California is warm.",
        source_start=0,
        source_end=34,
        order_index=0,
    )

    service = RAGService(db=mock_db, api_key="")
    service.client = None
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    service.clause_repo.list_by_document = MagicMock(return_value=[clause])

    res = service.chat("doc-2", "xyzqzk nonmatching term")
    assert "consult" in res["answer"].lower() or "not confident" in res["answer"].lower()
    assert res["confidence"] < 0.5
