import logging
import uuid

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.hash_service import HashService
from app.services.validation_service import FileValidationError, ValidationService
from app.storage.storage_service import StorageService
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DuplicateDocumentError(Exception):
    pass


class UploadService:

    def __init__(self, db: Session):
        self.db = db
        self.validation_service = ValidationService()
        self.hash_service = HashService()
        self.storage_service = StorageService()
        self.document_repository = DocumentRepository(db)

    async def upload(self, file: UploadFile) -> Document:
        logger.info(
            "Upload validation started",
            extra={
                "_event": "upload_started",
                "_filename": file.filename,
                "_content_type": file.content_type,
            },
        )

        try:
            validated_file = await self.validation_service.validate(file)
        except FileValidationError:
            logger.info(
                "Upload validation failed",
                extra={
                    "_event": "upload_validation_failed",
                    "_filename": file.filename,
                    "_content_type": file.content_type,
                },
            )
            raise

        sha256 = await self.hash_service.calculate_sha256(file)

        existing_document = self.document_repository.get_by_sha256(sha256)
        if existing_document is not None:
            logger.info(
                "Duplicate upload — returning existing document",
                extra={
                    "_event": "upload_duplicate_reused",
                    "_document_id": existing_document.id,
                    "_sha256": sha256,
                    "_filename": file.filename,
                },
            )
            return existing_document

        document_id = str(uuid.uuid4())
        stored_filename = f"{document_id}{validated_file.extension}"
        object_key = f"documents/raw/{stored_filename}"

        try:
            logger.info(
                "Object storage upload started",
                extra={
                    "_event": "storage_upload_started",
                    "_document_id": document_id,
                    "_object_key": object_key,
                    "_sha256": sha256,
                    "_file_size": validated_file.file_size,
                },
            )
            storage_uri = self.storage_service.upload_file(
                file_object=file.file,
                object_key=object_key,
                content_type=file.content_type,
            )
        except Exception:
            logger.exception(
                "Object storage upload failed",
                extra={
                    "_event": "storage_upload_failed",
                    "_document_id": document_id,
                    "_object_key": object_key,
                    "_sha256": sha256,
                },
            )
            raise

        document = Document(
            id=document_id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            mime_type=file.content_type,
            extension=validated_file.extension,
            storage_uri=storage_uri,
            object_key=object_key,
            file_size=validated_file.file_size,
            sha256=sha256,
            checksum_algorithm="SHA-256",
            status=DocumentStatus.QUEUED,
        )

        try:
            self.document_repository.create(document)
            self.db.commit()
            self.db.refresh(document)
        except IntegrityError:
            self.db.rollback()
            try:
                self.storage_service.delete_file(object_key)
            except Exception:
                logger.exception(
                    "Failed to clean up orphaned storage object: %s",
                    object_key,
                    extra={
                        "_event": "storage_cleanup_failed",
                        "_document_id": document_id,
                        "_object_key": object_key,
                    },
                )
            existing_document = self.document_repository.get_by_sha256(sha256)
            if existing_document is not None:
                return existing_document
            raise
        except Exception:
            self.db.rollback()
            try:
                self.storage_service.delete_file(object_key)
            except Exception:
                logger.exception(
                    "Failed to clean up orphaned storage object: %s",
                    object_key,
                    extra={
                        "_event": "storage_cleanup_failed",
                        "_document_id": document_id,
                        "_object_key": object_key,
                    },
                )
            raise

        logger.info(
            "Document upload completed",
            extra={
                "_event": "upload_completed",
                "_document_id": document.id,
                "_object_key": document.object_key,
                "_sha256": document.sha256,
                "_file_size": document.file_size,
                "_status": document.status.value,
            },
        )

        return document
