import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import settings
from app.models.ingestion import IngestionJob, OutboxEvent
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.ingestion_repository import IngestionRepository
from app.services.classification_service import ClauseClassificationService
from app.services.clause_service import ClauseSegmentationService
from app.services.explanation_service import ExplanationService
from app.schemas.ingestion import (
    CompleteDirectUploadRequest,
    IngestionQueuedResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.services.ocr_service import OCRService
from app.services.kafka_service import IngestionJobPayload, KafkaEventPublisher
from app.services.rag_service import RAGService
from app.services.risk_service import RiskService
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
        event_publisher: KafkaEventPublisher | None = None,
    ):
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.ingestion_repo = IngestionRepository(db)
        self._storage_service = storage_service
        self.event_publisher = event_publisher or KafkaEventPublisher()

    @property
    def storage_service(self) -> StorageService:
        if self._storage_service is None:
            self._storage_service = StorageService()
        return self._storage_service

    async def upload_via_api(self, file: UploadFile) -> Document:
        document = await UploadService(self.db).upload(file)
        self.enqueue_ingestion(
            document=document,
            processing_pool=self._default_processing_pool(document.extension),
        )
        return document

    def _default_processing_pool(self, extension: str) -> str:
        return "gpu" if extension.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tiff"} else "cpu"

    def enqueue_ingestion(
        self,
        document: Document,
        processing_pool: str,
    ) -> IngestionJob:
        existing_job = self.ingestion_repo.get_job_by_document_id(document.id)
        if existing_job is not None and existing_job.status in {"queued", "sharded", "processing"}:
            return existing_job

        job = self.ingestion_repo.create_job(
            IngestionJob(
                document_id=document.id,
                object_key=document.object_key,
                status="queued",
                processing_pool=processing_pool,
            )
        )
        payload = IngestionJobPayload(
            document_id=document.id,
            object_key=document.object_key,
            filename=document.original_filename,
            content_type=document.mime_type,
            file_size=document.file_size,
            sha256=document.sha256,
            processing_pool=processing_pool,
        )
        event = self.ingestion_repo.create_outbox_event(
            OutboxEvent(
                topic=settings.KAFKA_DOCUMENT_INGEST_TOPIC,
                aggregate_id=document.id,
                event_type="DocumentIngestRequested",
                payload={**payload.to_dict(), "job_id": job.id},
            )
        )
        self.db.commit()

        self.event_publisher.publish(
            topic=settings.KAFKA_DOCUMENT_INGEST_TOPIC,
            key=document.id,
            payload=event.payload,
        )
        self.ingestion_repo.mark_outbox_published(event)
        self.db.commit()
        return job

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

        job = self.enqueue_ingestion(
            document=document,
            processing_pool=request.processing_pool,
        )

        return IngestionQueuedResponse(
            document_id=document.id,
            status=document.status,
            object_key=document.object_key,
            queue_name=settings.KAFKA_DOCUMENT_INGEST_TOPIC,
            processing_pool=request.processing_pool,
            queued_at=datetime.now(UTC),
        )

    def run_text_ingestion_now(self, document_id: str):
        return OCRService(self.db).process_document(document_id)

    def segment_document(self, document_id: str, force: bool = False):
        return ClauseSegmentationService(self.db).segment_document(
            document_id=document_id,
            force=force,
        )

    def classify_document(self, document_id: str, force: bool = False):
        return ClauseClassificationService(self.db).classify_document(
            document_id=document_id,
            force=force,
        )

    def score_document_risk(self, document_id: str, force: bool = False):
        return RiskService(self.db).score_document_risk(
            document_id=document_id,
            force=force,
        )

    def explain_document(self, document_id: str, force: bool = False):
        return ExplanationService(self.db).explain_document(
            document_id=document_id,
            force=force,
        )

    def chat_with_document(self, document_id: str, query: str, top_k: int = 4):
        return RAGService(db=self.db).chat(
            document_id=document_id,
            query=query,
            top_k=top_k,
        )
