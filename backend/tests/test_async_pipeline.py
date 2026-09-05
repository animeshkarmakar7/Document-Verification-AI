from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.cqrs.commands import DocumentCommandHandler
from app.services.kafka_service import KafkaPublishError
from app.storage.storage_service import StorageService


@pytest.fixture
def client():
    return TestClient(app)


@patch("app.workers.tasks.analyze_document.delay")
def test_enqueue_ingestion_kafka_failure_degrades_gracefully(mock_delay):
    """Verify that when Kafka throws an error, enqueue_ingestion catches it and does not crash."""
    mock_db = MagicMock()
    mock_ingestion_repo = MagicMock()
    mock_ingestion_repo.get_job_by_document_id.return_value = None
    
    mock_job = MagicMock()
    mock_job.id = "test-job-123"
    mock_job.status = "queued"
    mock_ingestion_repo.create_job.return_value = mock_job

    mock_event = MagicMock()
    mock_event.payload = {"test": "data"}
    mock_ingestion_repo.create_outbox_event.return_value = mock_event

    mock_publisher = MagicMock()
    mock_publisher.publish.side_effect = KafkaPublishError("Kafka broker unreachable at localhost:9092")

    handler = DocumentCommandHandler(
        db=mock_db,
        event_publisher=mock_publisher,
    )
    handler.ingestion_repo = mock_ingestion_repo

    mock_doc = MagicMock(spec=Document)
    mock_doc.id = "doc-abc-123"
    mock_doc.object_key = "documents/raw/doc-abc-123.pdf"
    mock_doc.original_filename = "test.pdf"
    mock_doc.mime_type = "application/pdf"
    mock_doc.file_size = 1024
    mock_doc.sha256 = "a" * 64

    # This call should catch KafkaPublishError and succeed rather than raising an unhandled exception
    job = handler.enqueue_ingestion(document=mock_doc, processing_pool="cpu")

    assert job is not None
    assert job.status == "queued"
    mock_publisher.publish.assert_called_once()


def test_raw_upload_endpoint(client):
    """Verify PUT /api/v1/commands/documents/raw-upload/{object_key} accepts direct binary uploads."""
    payload = b"%PDF-1.4 test raw pdf binary content"
    object_key = "documents/raw/test-raw-upload.pdf"

    response = client.put(
        f"/api/v1/commands/documents/raw-upload/{object_key}",
        content=payload,
        headers={"Content-Type": "application/pdf"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "uploaded"
    assert data["object_key"] == object_key
    assert data["bytes_written"] == len(payload)

    # Verify bytes exist in storage
    storage = StorageService()
    assert storage.file_exists(object_key)
    downloaded = storage.download_file(object_key)
    assert downloaded == payload

    # Clean up test file
    storage.delete_file(object_key)


def test_presigned_upload_endpoint(client):
    """Verify POST /api/v1/commands/documents/presigned-upload returns valid URL and metadata."""
    req_body = {
        "filename": "sample_contract.pdf",
        "content_type": "application/pdf",
        "file_size": 2048,
    }

    response = client.post("/api/v1/commands/documents/presigned-upload", json=req_body)

    assert response.status_code == 201
    data = response.json()
    assert "document_id" in data
    assert "object_key" in data
    assert "upload_url" in data
    assert data["method"] == "PUT"
    assert "raw-upload" in data["upload_url"] or "http" in data["upload_url"]


def test_pipeline_status_endpoint_not_found(client):
    """Verify GET /api/v1/queries/documents/{id}/pipeline-status returns 404 for unknown document."""
    from app.api.dependencies import get_db
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    # Return None for get_by_id so query handler raises QueryNotFoundError
    mock_db.scalar.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/api/v1/queries/documents/nonexistent-id-123/pipeline-status")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)

