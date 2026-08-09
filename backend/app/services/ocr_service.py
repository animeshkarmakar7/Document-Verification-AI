import logging

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.ocr_result import OCRResult
from app.repositories.document_repository import DocumentRepository
from app.repositories.ocr_repository import OCRRepository
from app.services.ocr_extractor import LocalOCRExtractor, OCRExtractionError
from app.storage.storage_service import StorageService
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    """Raised when a document_id does not exist."""


class DocumentNotReadyForOCRError(Exception):
    """Raised when a document cannot be processed for OCR."""


class OCRService:

    def __init__(self, db: Session):
        self.db = db
        self.document_repository = DocumentRepository(db)
        self.ocr_repository = OCRRepository(db)
        self.storage_service = StorageService()
        self.extractor = LocalOCRExtractor()

    def process_document(
        self,
        document_id: str,
    ) -> OCRResult:

        document = self.document_repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        existing_result = self.ocr_repository.get_by_document_id(
            document_id
        )

        if existing_result is not None:
            return existing_result

        if document.status not in {
            DocumentStatus.QUEUED,
            DocumentStatus.FAILED,
            DocumentStatus.OCR_COMPLETE,
            DocumentStatus.CLAUSES_SEGMENTED,
            DocumentStatus.CLASSIFIED,
            DocumentStatus.RISK_SCORED,
            DocumentStatus.EXPLAINED,
        }:
            raise DocumentNotReadyForOCRError(
                f"Document is not ready for OCR. Current status: "
                f"{document.status.value}."
            )

        try:
            self._set_status(document, DocumentStatus.PROCESSING)

            logger.info(
                "OCR processing started",
                extra={
                    "_event": "ocr_started",
                    "_document_id": document.id,
                    "_object_key": document.object_key,
                },
            )

            content = self.storage_service.download_file(
                document.object_key
            )
            extraction = self.extractor.extract(
                content=content,
                extension=document.extension,
            )

            ocr_result = OCRResult(
                document_id=document.id,
                provider=self.extractor.provider,
                text=extraction.text,
                page_count=extraction.page_count,
                layout=extraction.layout,
            )

            self.ocr_repository.create(ocr_result)
            document.status = DocumentStatus.OCR_COMPLETE
            self.db.commit()
            self.db.refresh(ocr_result)

            logger.info(
                "OCR processing completed",
                extra={
                    "_event": "ocr_completed",
                    "_document_id": document.id,
                    "_page_count": ocr_result.page_count,
                    "_provider": ocr_result.provider,
                },
            )

            return ocr_result

        except OCRExtractionError:
            self._fail_document(document)
            raise

        except Exception:
            self._fail_document(document)
            logger.exception(
                "OCR processing failed",
                extra={
                    "_event": "ocr_failed",
                    "_document_id": document.id,
                },
            )
            raise

    def get_status(
        self,
        document_id: str,
    ) -> tuple[Document, bool]:

        document = self.document_repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        ocr_result = self.ocr_repository.get_by_document_id(document_id)

        return document, ocr_result is not None

    def get_result(
        self,
        document_id: str,
    ) -> OCRResult:

        document = self.document_repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        ocr_result = self.ocr_repository.get_by_document_id(document_id)

        if ocr_result is None:
            raise DocumentNotReadyForOCRError(
                "OCR result is not available yet."
            )

        return ocr_result

    def _set_status(
        self,
        document: Document,
        status: DocumentStatus,
    ) -> None:
        document.status = status
        self.db.commit()

    def _fail_document(
        self,
        document: Document,
    ) -> None:
        document.status = DocumentStatus.FAILED
        self.db.commit()
