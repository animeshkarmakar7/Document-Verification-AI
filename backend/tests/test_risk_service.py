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


def test_get_risk_dashboard_enriched_metadata(mock_db):
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
        status=DocumentStatus.EXPLAINED,
    )
    clause = Clause(
        id="clause-pk-1",
        document_id="doc-123",
        clause_id="doc-123-clause-0001",
        text="Tenant shall pay penalty of 20% on delayed rent.",
        source_start=15,
        source_end=65,
        heading="2. Penalties and Fees",
        order_index=1,
    )
    risk = ClauseRisk(
        id="risk-pk-1",
        document_id="doc-123",
        clause_id="doc-123-clause-0001",
        clause_pk="clause-pk-1",
        risk_level=RiskLevel.HIGH,
        risk_score=0.85,
        risk_reason="Unreasonable financial penalty fee.",
        flag_type=RiskFlagType.UNFAIR_TERM,
        suggested_mitigation="Cap penalty fee at 5%",
    )
    classification = ClauseClassification(
        id="class-pk-1",
        document_id="doc-123",
        clause_id="doc-123-clause-0001",
        clause_pk="clause-pk-1",
        category=ClauseCategory.PENALTY_FEES,
        model_version="gemini-3.6-flash",
    )

    service = RiskService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    service.risk_repo.list_by_document = MagicMock(return_value=[risk])
    service.clause_repo.list_by_document = MagicMock(return_value=[clause])
    service.class_repo.list_by_document = MagicMock(return_value=[classification])
    service.ocr_repo.get_by_document_id = MagicMock(return_value=None)

    mock_expl = MagicMock()
    mock_expl.clause_id = "doc-123-clause-0001"
    mock_expl.plain_summary = "You will be charged a 20% extra fee if rent is late."
    service.expl_repo.list_by_document = MagicMock(return_value=[mock_expl])

    dashboard = service.get_risk_dashboard("doc-123")
    assert dashboard["total_clauses"] == 1
    assert dashboard["high_risk_count"] == 1
    assert len(dashboard["clauses"]) == 1

    clause_item = dashboard["clauses"][0]
    assert clause_item["section_heading"] == "2. Penalties and Fees"
    assert clause_item["page_number"] == 1
    assert clause_item["plain_summary"] == "You will be charged a 20% extra fee if rent is late."
    assert clause_item["risk_category"] == "FINANCIAL"
    assert "Tenant shall pay penalty" in clause_item["verbatim_text"]

