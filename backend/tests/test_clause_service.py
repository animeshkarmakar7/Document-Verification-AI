"""Unit tests for ClauseSegmentationService.

Coverage:
- segment_document: happy path, idempotent (no-force), force re-segment
- segment_document: missing OCR result → DocumentNotReadyForSegmentationError
- segment_document: document not found → DocumentNotFoundError
- get_clause: found
- get_clause: clause not found → ClauseNotFoundError
- get_clause: document not found → DocumentNotFoundError
- list_clauses_paginated: returns (clauses, total)
- list_clauses_paginated: document not found
"""

from datetime import UTC, datetime
from typing import ClassVar

import pytest
from app.models.clause import Clause
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.ocr_result import OCRResult
from app.services.clause_service import (
    ClauseNotFoundError,
    ClauseSegmentationService,
    DocumentNotReadyForSegmentationError,
)
from app.services.ocr_service import DocumentNotFoundError

# ---------------------------------------------------------------------------
# Fake collaborators
# ---------------------------------------------------------------------------

_OCR_TEXT = (
    "1. Rent\n"
    "The tenant shall pay monthly.\n\n"
    "2. Termination\n"
    "Either party may terminate with notice."
)


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


class FakeOCRRepository:
    result: ClassVar[OCRResult | None] = None

    def __init__(self, db):
        self.db = db

    def get_by_document_id(self, document_id):
        if self.result and self.result.document_id == document_id:
            return self.result
        return None


class FakeClauseRepository:
    clauses: ClassVar[list[Clause]] = []

    def __init__(self, db):
        self.db = db

    def list_by_document_id(
        self,
        document_id,
        limit=None,
        offset=0,
    ):
        rows = [c for c in self.clauses if c.document_id == document_id]
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    def count_by_document_id(self, document_id):
        return sum(1 for c in self.clauses if c.document_id == document_id)

    def get_by_clause_id(self, document_id, clause_id):
        for clause in self.clauses:
            if (
                clause.document_id == document_id
                and clause.clause_id == clause_id
            ):
                return clause
        return None

    def create_many(self, clauses):
        now = datetime.now(UTC)
        for clause in clauses:
            clause.created_at = now
        self.clauses.extend(clauses)
        return clauses

    def delete_by_document_id(self, document_id):
        self.clauses = [
            c for c in self.clauses if c.document_id != document_id
        ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    FakeClauseRepository.clauses = []
    FakeDocumentRepository.document = Document(
        id="document-1",
        original_filename="contract.pdf",
        stored_filename="document-1.pdf",
        mime_type="application/pdf",
        extension=".pdf",
        storage_uri="s3://legal-documents/documents/raw/document-1.pdf",
        object_key="documents/raw/document-1.pdf",
        file_size=100,
        sha256="a" * 64,
        checksum_algorithm="SHA-256",
        status=DocumentStatus.OCR_COMPLETE,
    )
    FakeOCRRepository.result = OCRResult(
        document_id="document-1",
        provider="local-text-extractor",
        text=_OCR_TEXT,
        page_count=1,
        layout={"pages": []},
    )

    monkeypatch.setattr(
        "app.services.clause_service.DocumentRepository",
        FakeDocumentRepository,
    )
    monkeypatch.setattr(
        "app.services.clause_service.OCRRepository",
        FakeOCRRepository,
    )
    monkeypatch.setattr(
        "app.services.clause_service.ClauseRepository",
        FakeClauseRepository,
    )


def _make_service():
    return ClauseSegmentationService(FakeDb())


# ---------------------------------------------------------------------------
# segment_document
# ---------------------------------------------------------------------------


def test_segment_document_persists_clauses_and_updates_status():
    service = _make_service()

    clauses = service.segment_document("document-1")

    assert len(clauses) == 2
    assert clauses[0].clause_id == "document-1-clause-0001"
    assert clauses[0].source_start == 0
    assert FakeDocumentRepository.document.status == (
        DocumentStatus.CLAUSES_SEGMENTED
    )


def test_segment_document_returns_existing_clauses_without_force():
    existing = Clause(
        document_id="document-1",
        clause_id="document-1-clause-0001",
        order_index=1,
        heading="Existing",
        text="Existing text",
        source_start=0,
        source_end=13,
    )
    FakeClauseRepository.clauses = [existing]

    clauses = _make_service().segment_document("document-1")

    assert clauses == [existing]


def test_segment_document_force_rebuilds_clauses():
    existing = Clause(
        document_id="document-1",
        clause_id="document-1-clause-0001",
        order_index=1,
        heading="Old",
        text="Old text",
        source_start=0,
        source_end=8,
    )
    FakeClauseRepository.clauses = [existing]

    clauses = _make_service().segment_document("document-1", force=True)

    # Old clause was deleted; fresh segmentation produced 2 new ones.
    assert len(clauses) == 2
    assert all(c.heading != "Old" for c in clauses)


def test_segment_document_requires_ocr_result():
    FakeOCRRepository.result = None
    with pytest.raises(DocumentNotReadyForSegmentationError):
        _make_service().segment_document("document-1")


def test_segment_document_raises_when_document_not_found():
    with pytest.raises(DocumentNotFoundError):
        _make_service().segment_document("nonexistent-id")


# ---------------------------------------------------------------------------
# get_clause
# ---------------------------------------------------------------------------


def test_get_clause_returns_correct_clause():
    # First seed clauses via segment_document so FakeClauseRepository is populated.
    service = _make_service()
    service.segment_document("document-1")

    clause = service.get_clause("document-1", "document-1-clause-0001")
    assert clause.clause_id == "document-1-clause-0001"


def test_get_clause_raises_clause_not_found():
    _make_service().segment_document("document-1")

    with pytest.raises(ClauseNotFoundError):
        _make_service().get_clause("document-1", "document-1-clause-9999")


def test_get_clause_raises_document_not_found():
    with pytest.raises(DocumentNotFoundError):
        _make_service().get_clause("nonexistent-id", "some-clause")


# ---------------------------------------------------------------------------
# list_clauses_paginated
# ---------------------------------------------------------------------------


def test_list_clauses_paginated_returns_all_with_total():
    _make_service().segment_document("document-1")

    clauses, total = _make_service().list_clauses_paginated("document-1")

    assert total == 2
    assert len(clauses) == 2


def test_list_clauses_paginated_with_limit():
    _make_service().segment_document("document-1")

    clauses, total = _make_service().list_clauses_paginated(
        "document-1", limit=1
    )

    assert total == 2
    assert len(clauses) == 1
    assert clauses[0].order_index == 1


def test_list_clauses_paginated_with_offset():
    _make_service().segment_document("document-1")

    clauses, total = _make_service().list_clauses_paginated(
        "document-1", offset=1
    )

    assert total == 2
    assert len(clauses) == 1
    assert clauses[0].order_index == 2


def test_list_clauses_paginated_raises_document_not_found():
    with pytest.raises(DocumentNotFoundError):
        _make_service().list_clauses_paginated("nonexistent-id")
