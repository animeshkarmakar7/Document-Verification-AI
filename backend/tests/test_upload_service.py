from datetime import UTC, datetime
from io import BytesIO
from typing import ClassVar

import pytest
from app.models.enums import DocumentStatus
from app.services.upload_service import DuplicateDocumentError, UploadService
from fastapi import UploadFile


class FakeDb:
    def commit(self):
        pass

    def refresh(self, document):
        document.created_at = datetime.now(UTC)

    def rollback(self):
        pass


class FakeRepository:
    documents_by_sha256: ClassVar[dict[str, object]] = {}

    def __init__(self, db):
        self.db = db

    def get_by_sha256(self, sha256):
        return self.documents_by_sha256.get(sha256)

    def create(self, document):
        self.documents_by_sha256[document.sha256] = document
        return document


class FakeStorage:
    uploaded: ClassVar[dict[str, dict[str, object]]] = {}

    def upload_file(self, file_object, object_key, content_type):
        self.uploaded[object_key] = {
            "content": file_object.read(),
            "content_type": content_type,
        }
        return f"s3://legal-documents/{object_key}"

    def delete_file(self, object_key):
        self.uploaded.pop(object_key, None)


@pytest.fixture(autouse=True)
def reset_fakes(monkeypatch):
    FakeRepository.documents_by_sha256 = {}
    FakeStorage.uploaded = {}

    monkeypatch.setattr(
        "app.services.upload_service.DocumentRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        "app.services.upload_service.StorageService",
        FakeStorage,
    )


def make_pdf_upload(content=b"%PDF-1.7\nlegal document"):
    return UploadFile(
        file=BytesIO(content),
        filename="contract.pdf",
        headers={
            "content-type": "application/pdf",
        },
    )


@pytest.mark.anyio
async def test_upload_persists_ocr_ready_document():
    service = UploadService(FakeDb())

    document = await service.upload(make_pdf_upload())

    assert document.id
    assert document.status == DocumentStatus.QUEUED
    assert document.object_key.startswith("documents/raw/")
    assert document.storage_uri.endswith(document.object_key)
    assert document.checksum_algorithm == "SHA-256"
    assert FakeStorage.uploaded[document.object_key]["content"].startswith(
        b"%PDF-"
    )


@pytest.mark.anyio
async def test_upload_rejects_duplicate_sha256():
    service = UploadService(FakeDb())

    first_document = await service.upload(make_pdf_upload())
    duplicate_upload = make_pdf_upload()

    with pytest.raises(DuplicateDocumentError):
        await service.upload(duplicate_upload)

    assert len(FakeRepository.documents_by_sha256) == 1
    assert first_document.sha256 in FakeRepository.documents_by_sha256
