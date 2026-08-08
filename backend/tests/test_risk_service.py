from datetime import UTC, datetime
from unittest.mock import MagicMock
import pytest

from app.models.classification import ClauseClassification
from app.models.clause import Clause
from app.models.document import Document
from app.models.enums import ClauseCategory, DocumentStatus, RiskFlagType, RiskLevel
from app.models.risk import ClauseRisk
from app.services.risk_evaluator import ClauseRiskItem
from app.services.risk_service import (
    DocumentNotFoundError,
    InvalidDocumentStatusError,
    RiskService,
)


@pytest.fixture
def mock_db():
    return MagicMock()


def test_score_document_risk_doc_not_found(mock_db):
    service = RiskService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=None)
    with pytest.raises(DocumentNotFoundError):
        service.score_document_risk("nonexistent-doc")


def test_score_document_risk_invalid_status(mock_db):
    doc = Document(
        id="doc-123",
        original_filename="doc.pdf",
        stored_filename="stored.pdf",
        mime_type="application/pdf",
        extension="pdf",
        storage_uri="/tmp/doc.pdf",
        object_key="doc-123.pdf",
        file_size=1024,
        sha256="dummyhash1234567890",
        status=DocumentStatus.UPLOADED,
    )
    service = RiskService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    with pytest.raises(InvalidDocumentStatusError):
        service.score_document_risk("doc-123")


def test_score_document_risk_success(mock_db):
    doc = Document(
        id="doc-123",
        original_filename="doc.pdf",
        stored_filename="stored.pdf",
        mime_type="application/pdf",
        extension="pdf",
        storage_uri="/tmp/doc.pdf",
        object_key="doc-123.pdf",
        file_size=1024,
        sha256="dummyhash1234567890",
        status=DocumentStatus.CLASSIFIED,
    )
    clause = Clause(
        id="clause-pk-1",
        document_id="doc-123",
        clause_id="doc-123-clause-0001",
        text="Landlord may enter without notice.",
        source_start=0,
        source_end=35,
        order_index=0,
    )
    classification = ClauseClassification(
        id="class-pk-1",
        document_id="doc-123",
        clause_id="doc-123-clause-0001",
        clause_pk="clause-pk-1",
        category=ClauseCategory.TERMINATION_EXIT,
        model_version="gemini-3.6-flash",
    )

    service = RiskService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    service.risk_repo.list_by_document = MagicMock(return_value=[])
    service.clause_repo.list_by_document = MagicMock(return_value=[clause])
    service.class_repo.list_by_document = MagicMock(return_value=[classification])
    service.evaluator.evaluate_batch = MagicMock(
        return_value=[
            ClauseRiskItem(
                clause_id="doc-123-clause-0001",
                risk_level=RiskLevel.HIGH,
                risk_score=0.8,
                risk_reason="Unilateral access without notice",
                flag_type=RiskFlagType.UNFAIR_TERM,
                suggested_mitigation="Require 24h written notice",
            )
        ]
    )
    service.risk_repo.create_many = MagicMock(side_effect=lambda items: items)

    saved = service.score_document_risk("doc-123")
    assert len(saved) == 1
    assert saved[0].risk_level == RiskLevel.HIGH
    assert saved[0].risk_score == 0.8
    assert doc.status == DocumentStatus.RISK_SCORED
