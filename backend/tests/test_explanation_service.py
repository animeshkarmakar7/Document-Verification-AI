from datetime import UTC, datetime
from unittest.mock import MagicMock
import pytest

from app.models.clause import Clause
from app.models.classification import ClauseClassification
from app.models.document import Document
from app.models.enums import ClauseCategory, DocumentStatus
from app.models.explanation import ClauseExplanation
from app.services.gemini_explainer import ClauseExplanationItem
from app.services.explanation_service import (
    DocumentNotFoundError,
    ExplanationService,
    InvalidDocumentStatusError,
)


@pytest.fixture
def mock_db():
    return MagicMock()


def test_explain_document_not_found(mock_db):
    service = ExplanationService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=None)
    with pytest.raises(DocumentNotFoundError):
        service.explain_document("nonexistent-doc")


def test_explain_document_invalid_status(mock_db):
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
        status=DocumentStatus.UPLOADED,
    )
    service = ExplanationService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    with pytest.raises(InvalidDocumentStatusError):
        service.explain_document("doc-1")


def test_explain_document_success(mock_db):
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
        status=DocumentStatus.RISK_SCORED,
    )
    clause = Clause(
        id="clause-pk-1",
        document_id="doc-1",
        clause_id="doc-1-clause-0001",
        text="Landlord may terminate without notice at any time.",
        source_start=0,
        source_end=50,
        order_index=0,
    )
    classification = ClauseClassification(
        id="class-pk-1",
        document_id="doc-1",
        clause_id="doc-1-clause-0001",
        clause_pk="clause-pk-1",
        category=ClauseCategory.TERMINATION_EXIT,
        model_version="gemini-3.6-flash",
    )

    service = ExplanationService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    service.expl_repo.list_by_document = MagicMock(return_value=[])
    service.clause_repo.list_by_document = MagicMock(return_value=[clause])
    service.class_repo.list_by_document = MagicMock(return_value=[classification])
    service.explainer.explain_batch = MagicMock(
        return_value=[
            ClauseExplanationItem(
                clause_id="doc-1-clause-0001",
                plain_summary="The landlord can end your tenancy at any time without warning.",
                confidence=0.9,
                is_grounded=True,
            )
        ]
    )
    service.expl_repo.create_many = MagicMock(side_effect=lambda items: items)

    saved = service.explain_document("doc-1")
    assert len(saved) == 1
    assert saved[0].plain_summary == "The landlord can end your tenancy at any time without warning."
    assert saved[0].is_grounded is True
    assert doc.status == DocumentStatus.EXPLAINED


def test_explain_low_confidence_replaces_summary(mock_db):
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
        status=DocumentStatus.RISK_SCORED,
    )
    clause = Clause(
        id="clause-pk-2",
        document_id="doc-2",
        clause_id="doc-2-clause-0001",
        text="As applicable.",
        source_start=0,
        source_end=14,
        order_index=0,
    )

    service = ExplanationService(db=mock_db)
    service.doc_repo.get_by_id = MagicMock(return_value=doc)
    service.expl_repo.list_by_document = MagicMock(return_value=[])
    service.clause_repo.list_by_document = MagicMock(return_value=[clause])
    service.class_repo.list_by_document = MagicMock(return_value=[])
    service.explainer.explain_batch = MagicMock(
        return_value=[
            ClauseExplanationItem(
                clause_id="doc-2-clause-0001",
                plain_summary="Unclear clause.",
                confidence=0.4,
                is_grounded=False,
            )
        ]
    )
    service.expl_repo.create_many = MagicMock(side_effect=lambda items: items)

    saved = service.explain_document("doc-2")
    assert len(saved) == 1
    assert "consult" in saved[0].plain_summary.lower()
    assert saved[0].is_grounded is False
