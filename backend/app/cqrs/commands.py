import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import settings
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.schemas.ingestion import (
    CompleteDirectUploadRequest,
    IngestionQueuedResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.services.ocr_service import OCRService
from app.services.queue_service import IngestionJobPayload, QueuePublisher
from app.services.upload_service import UploadService
from app.services.validation_service import EXTENSION_MIME_TYPES, SUPPORTED_EXTENSIONS
from app.storage.storage_service import StorageService
from fastapi import UploadFile
from sqlalchemy.orm import Session


class CommandValidationError(Exception):
    pass


class DocumentCommandHandler:
    def __init__(
        self,
        db: Session,
        storage_service: StorageService | None = None,
        queue_publisher: QueuePublisher | None = None,
    ):
        self.db = db
        self.document_repo = DocumentRepository(db)
        self._storage_service = storage_service
        self.queue_publisher = queue_publisher

    @property
    def storage_service(self) -> StorageService:
        if self._storage_service is None:
            self._storage_service = StorageService()
        return self._storage_service

    async def upload_via_api(self, file: UploadFile) -> Document:
        return await UploadService(self.db).upload(file)

    def create_presigned_upload(
        self,
        request: PresignedUploadRequest,
    ) -> PresignedUploadResponse:
        extension = Path(request.filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise CommandValidationError(f"Unsupported file extension: {extension}")

        allowed_content_types = EXTENSION_MIME_TYPES[extension]
        if request.content_type not in allowed_content_types:
            raise CommandValidationError(
                "File extension and content type do not match."
            )

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if request.file_size > max_bytes:
            raise CommandValidationError(
                f"File exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        document_id = str(uuid.uuid4())
        object_key = f"documents/raw/{document_id}{extension}"
        upload_url = self.storage_service.create_presigned_put_url(
            object_key=object_key,
            content_type=request.content_type,
            expires_in=settings.PRESIGNED_UPLOAD_EXPIRY_SECONDS,
        )

        return PresignedUploadResponse(
            document_id=document_id,
            object_key=object_key,
            upload_url=upload_url,
            expires_in_seconds=settings.PRESIGNED_UPLOAD_EXPIRY_SECONDS,
            required_headers={"Content-Type": request.content_type},
        )

    def complete_direct_upload(
        self,
        request: CompleteDirectUploadRequest,
    ) -> IngestionQueuedResponse:
        extension = Path(request.filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise CommandValidationError(f"Unsupported file extension: {extension}")

        existing_document = self.document_repo.get_by_sha256(request.sha256)
        if existing_document is not None:
            document = existing_document
        else:
            document = Document(
                id=request.document_id,
                original_filename=request.filename,
                stored_filename=Path(request.object_key).name,
                mime_type=request.content_type,
                extension=extension,
                storage_uri=f"s3://{settings.STORAGE_BUCKET}/{request.object_key}",
                object_key=request.object_key,
                file_size=request.file_size,
                sha256=request.sha256,
                checksum_algorithm="SHA-256",
                status=DocumentStatus.QUEUED,
            )
            self.document_repo.create(document)
            self.db.commit()
            self.db.refresh(document)

        payload = IngestionJobPayload(
            document_id=document.id,
            object_key=document.object_key,
            filename=document.original_filename,
            content_type=document.mime_type,
            file_size=document.file_size,
            sha256=document.sha256,
            processing_pool=request.processing_pool,
        )

        if self.queue_publisher is not None:
            self.queue_publisher.publish(
                settings.INGESTION_QUEUE_NAME,
                payload.to_dict(),
            )

        return IngestionQueuedResponse(
            document_id=document.id,
            status=document.status,
            object_key=document.object_key,
            queue_name=settings.INGESTION_QUEUE_NAME,
            processing_pool=request.processing_pool,
            queued_at=datetime.now(UTC),
        )

    def run_text_ingestion_now(self, document_id: str):
        return OCRService(self.db).process_document(document_id)
