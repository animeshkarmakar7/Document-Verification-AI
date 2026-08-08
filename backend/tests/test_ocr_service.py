from datetime import UTC, datetime
from typing import ClassVar

import pytest
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.ocr_result import OCRResult
from app.services.ocr_extractor import OCRExtraction, OCRExtractionError
from app.services.ocr_service import OCRService


class FakeDb:
    def commit(self):
        pass

    def refresh(self, model):
        if getattr(model, "created_at", None) is None:
            model.created_at = datetime.now(UTC)


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

    def create(self, ocr_result):
        self.result = ocr_result
        return ocr_result


class FakeStorage:
    def download_file(self, object_key):
        return b"fake document bytes"


class FakeExtractor:
    provider = "fake-ocr"

    def extract(self, content, extension):
        return OCRExtraction(
            text="Extracted legal text",
            page_count=1,
            layout={
                "pages": [
                    {
                        "page_number": 1,
                        "text": "Extracted legal text",
                    }
                ]
            },
        )


class FailingExtractor:
    provider = "fake-ocr"

    def extract(self, content, extension):
        raise OCRExtractionError("OCR failed")


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    FakeOCRRepository.result = None
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
        status=DocumentStatus.QUEUED,
    )

    monkeypatch.setattr(
        "app.services.ocr_service.DocumentRepository",
        FakeDocumentRepository,
    )
    monkeypatch.setattr(
        "app.services.ocr_service.OCRRepository",
        FakeOCRRepository,
    )
    monkeypatch.setattr(
        "app.services.ocr_service.StorageService",
        FakeStorage,
    )
    monkeypatch.setattr(
        "app.services.ocr_service.LocalOCRExtractor",
        FakeExtractor,
    )


def test_process_document_stores_ocr_result():
    service = OCRService(FakeDb())

    ocr_result = service.process_document("document-1")

    assert ocr_result.text == "Extracted legal text"
    assert ocr_result.page_count == 1
    assert ocr_result.provider == "fake-ocr"
    assert FakeDocumentRepository.document.status == DocumentStatus.OCR_COMPLETE


def test_process_document_marks_failed_when_extraction_fails():
    service = OCRService(FakeDb())
    service.extractor = FailingExtractor()

    with pytest.raises(OCRExtractionError):
        service.process_document("document-1")

    assert FakeDocumentRepository.document.status == DocumentStatus.FAILED
