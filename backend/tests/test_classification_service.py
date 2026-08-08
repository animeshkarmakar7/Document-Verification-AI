from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from app.models.classification import ClauseClassification
from app.models.clause import Clause
from app.models.document import Document
from app.models.enums import ClauseCategory, DocumentStatus
from app.services.classification_service import (
    ClassificationNotFoundError,
    ClauseClassificationService,
    DocumentNotReadyForClassificationError,
)
from app.services.gemini_classifier import ClassificationResult
from app.services.ocr_service import DocumentNotFoundError


class FakeDb:
    def commit(self):
        pass


class FakeDocumentRepository:
    document: ClassVar[Document | None] = None

    def __init__(self, db):
        self.db = db

    def get_by_id(self, document_id):
        if self.document and self.document.id == document_id:
            return self.document
        return None


class FakeClauseRepository:
    clauses: ClassVar[list[Clause]] = []

    def __init__(self, db):
        self.db = db

    def list_by_document_id(self, document_id):
        return [c for c in self.clauses if c.document_id == document_id]


class FakeClassificationRepository:
    classifications: ClassVar[list[ClauseClassification]] = []

    def __init__(self, db):
        self.db = db

    def list_by_document_id(self, document_id):
        return [c for c in self.classifications if c.document_id == document_id]

    def get_by_clause_id(self, document_id, clause_id):
        for c in self.classifications:
            if c.document_id == document_id and c.clause_id == clause_id:
                return c
        return None

    def create_many(self, items):
        now = datetime.now(UTC)
        for item in items:
            item.created_at = now
        self.classifications.extend(items)
        return items

    def delete_by_document_id(self, document_id):
        self.classifications = [
            c for c in self.classifications if c.document_id != document_id
        ]


@pytest.fixture(autouse=True)
def patch_repositories(monkeypatch):
    FakeClassificationRepository.classifications = []
    FakeClauseRepository.clauses = [
        Clause(
            id="pk-1",
            document_id="doc-1",
            clause_id="doc-1-clause-0001",
            order_index=1,
            heading="1. Rent",
            text="Tenant pays monthly.",
            source_start=0,
            source_end=20,
        ),
        Clause(
            id="pk-2",
            document_id="doc-1",
            clause_id="doc-1-clause-0002",
            order_index=2,
            heading="2. Term",
            text="Termination notice.",
            source_start=21,
            source_end=40,
        ),
    ]

    FakeDocumentRepository.document = Document(
        id="doc-1",
        original_filename="contract.pdf",
        stored_filename="doc-1.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        storage_uri="s3://doc-1.pdf",
        object_key="documents/raw/doc-1.pdf",
        file_size=100,
        sha256="a" * 64,
        checksum_algorithm="SHA-256",
        status=DocumentStatus.CLAUSES_SEGMENTED,
    )

    monkeypatch.setattr(
        "app.services.classification_service.DocumentRepository",
        FakeDocumentRepository,
    )
    monkeypatch.setattr(
        "app.services.classification_service.ClauseRepository",
        FakeClauseRepository,
    )
    monkeypatch.setattr(
        "app.services.classification_service.ClassificationRepository",
        FakeClassificationRepository,
    )


def test_classify_document_success():
    mock_classifier = MagicMock()
    mock_classifier.model_name = "gemini-2.0-flash"
    mock_classifier.classify_batch.return_value = [
        ClassificationResult(
            clause_id="doc-1-clause-0001",
            category=ClauseCategory.PAYMENT,
            raw_response={"category": "PAYMENT"},
        ),
        ClassificationResult(
            clause_id="doc-1-clause-0002",
            category=ClauseCategory.TERMINATION,
            raw_response={"category": "TERMINATION"},
        ),
    ]

    service = ClauseClassificationService(FakeDb(), classifier=mock_classifier)
    res = service.classify_document("doc-1")

    assert len(res) == 2
    assert res[0].category == ClauseCategory.PAYMENT
    assert res[1].category == ClauseCategory.TERMINATION
    assert FakeDocumentRepository.document.status == DocumentStatus.CLASSIFIED


def test_classify_document_not_ready():
    FakeDocumentRepository.document.status = DocumentStatus.QUEUED
    service = ClauseClassificationService(FakeDb())
    with pytest.raises(DocumentNotReadyForClassificationError):
        service.classify_document("doc-1")


def test_classify_document_not_found():
    service = ClauseClassificationService(FakeDb())
    with pytest.raises(DocumentNotFoundError):
        service.classify_document("nonexistent")


def test_list_classifications_and_get_clause_classification():
    existing = ClauseClassification(
        document_id="doc-1",
        clause_pk="pk-1",
        clause_id="doc-1-clause-0001",
        category=ClauseCategory.PAYMENT,
        model_version="gemini-2.0-flash",
        raw_response={},
        source_start=0,
        source_end=20,
    )
    FakeClassificationRepository.classifications = [existing]

    service = ClauseClassificationService(FakeDb())
    items = service.list_classifications("doc-1")
    assert len(items) == 1

    single = service.get_clause_classification("doc-1", "doc-1-clause-0001")
    assert single.category == ClauseCategory.PAYMENT


def test_get_clause_classification_not_found():
    service = ClauseClassificationService(FakeDb())
    with pytest.raises(ClassificationNotFoundError):
        service.get_clause_classification("doc-1", "missing-clause")
