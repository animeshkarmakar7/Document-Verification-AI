from datetime import datetime

from app.models.enums import DocumentStatus
from pydantic import BaseModel, Field


class PresignedUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str
    file_size: int = Field(..., gt=0)


class PresignedUploadResponse(BaseModel):
    document_id: str
    object_key: str
    upload_url: str
    expires_in_seconds: int
    method: str = "PUT"
    required_headers: dict[str, str]


class CompleteDirectUploadRequest(BaseModel):
    document_id: str
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str
    file_size: int = Field(..., gt=0)
    sha256: str = Field(..., min_length=64, max_length=64)
    object_key: str
    processing_pool: str = Field(default="cpu", pattern="^(cpu|gpu)$")


class IngestionQueuedResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    object_key: str
    queue_name: str
    processing_pool: str
    queued_at: datetime


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    original_filename: str
    object_key: str
    created_at: datetime
    updated_at: datetime


class PipelineStatusResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    stage: str
    progress_percent: int
    clause_count: int = 0
    page_count: int | None = None
    error_message: str | None = None
    is_complete: bool = False
    is_failed: bool = False
