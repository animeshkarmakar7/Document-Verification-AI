import logging

from app.models.clause import Clause
from app.models.enums import DocumentStatus
from app.repositories.clause_repository import ClauseRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.ocr_repository import OCRRepository
from app.services.clause_segmenter import ClauseSegmenter
from app.services.ocr_service import DocumentNotFoundError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DocumentNotReadyForSegmentationError(Exception):
    """Raised when OCR text is unavailable for clause segmentation."""


class ClauseNotFoundError(Exception):
    """Raised when a specific clause_id does not exist for a document."""


class ClauseSegmentationService:

    def __init__(self, db: Session):
        self.db = db
        self.document_repository = DocumentRepository(db)
        self.ocr_repository = OCRRepository(db)
        self.clause_repository = ClauseRepository(db)
        self.segmenter = ClauseSegmenter()

    def segment_document(
        self,
        document_id: str,
        force: bool = False,
    ) -> list[Clause]:

        document = self.document_repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        existing_clauses = (
            self.clause_repository.list_by_document_id(document_id)
        )

        if existing_clauses and not force:
            return existing_clauses

        ocr_result = self.ocr_repository.get_by_document_id(document_id)

        if (
            ocr_result is None
            or document.status
            not in {
                DocumentStatus.OCR_COMPLETE,
                DocumentStatus.CLAUSES_SEGMENTED,
            }
        ):
            raise DocumentNotReadyForSegmentationError(
                "Document must have OCR_COMPLETE status before "
                "clause segmentation."
            )

        segmented_clauses = self.segmenter.segment(
            document_id=document.id,
            text=ocr_result.text,
        )

        if not segmented_clauses:
            raise DocumentNotReadyForSegmentationError(
                "OCR text is empty; no clauses can be segmented."
            )

        if existing_clauses and force:
            self.clause_repository.delete_by_document_id(document_id)

        clauses = [
            Clause(
                document_id=document.id,
                clause_id=segmented_clause.clause_id,
                order_index=segmented_clause.order_index,
                heading=segmented_clause.heading,
                text=segmented_clause.text,
                source_start=segmented_clause.source_start,
                source_end=segmented_clause.source_end,
            )
            for segmented_clause in segmented_clauses
        ]

        self.clause_repository.create_many(clauses)
        document.status = DocumentStatus.CLAUSES_SEGMENTED
        self.db.commit()

        logger.info(
            "Clause segmentation completed",
            extra={
                "_event": "clause_segmentation_completed",
                "_document_id": document.id,
                "_clause_count": len(clauses),
            },
        )

        return clauses

    def get_clause(
        self,
        document_id: str,
        clause_id: str,
    ) -> Clause:
        """Return a single clause by its stable clause_id string.

        Raises
        ------
        DocumentNotFoundError
            When the parent document does not exist.
        ClauseNotFoundError
            When no clause with the given clause_id exists for the document.
        """

        document = self.document_repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        clause = self.clause_repository.get_by_clause_id(
            document_id, clause_id
        )

        if clause is None:
            raise ClauseNotFoundError(
                f"Clause '{clause_id}' not found for document "
                f"'{document_id}'."
            )

        return clause

    def list_clauses(
        self,
        document_id: str,
    ) -> list[Clause]:

        document = self.document_repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        return self.clause_repository.list_by_document_id(document_id)

    def list_clauses_paginated(
        self,
        document_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Clause], int]:
        """Return a page of clauses and the total count for the document.

        Returns
        -------
        tuple[list[Clause], int]
            ``(clauses, total)`` where *total* is the unpaged row count.

        Raises
        ------
        DocumentNotFoundError
            When the parent document does not exist.
        """

        document = self.document_repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError("Document not found.")

        total = self.clause_repository.count_by_document_id(document_id)
        clauses = self.clause_repository.list_by_document_id(
            document_id,
            limit=limit,
            offset=offset,
        )

        return clauses, total
