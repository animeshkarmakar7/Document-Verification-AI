import logging

from app.config.settings import settings
from app.models.classification import ClauseClassification
from app.models.enums import ClauseCategory, DocumentStatus
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.clause_repository import ClauseRepository
from app.repositories.document_repository import DocumentRepository
from app.services.gemini_classifier import ClassificationResult, GeminiClassifier
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DocumentNotReadyForClassificationError(Exception):
    pass


class ClassificationNotFoundError(Exception):
    pass


class ClauseClassificationService:

    def __init__(
        self,
        db: Session,
        classifier: GeminiClassifier | None = None,
    ):
        self.db = db
        self.document_repository = DocumentRepository(db)
        self.clause_repository = ClauseRepository(db)
        self.classification_repository = ClassificationRepository(db)
        self.classifier = classifier or GeminiClassifier()

    def classify_document(
        self,
        document_id: str,
        force: bool = False,
    ) -> list[ClauseClassification]:
        document = self.document_repository.get_by_id(document_id)
        if not document:
            from app.services.ocr_service import DocumentNotFoundError

            raise DocumentNotFoundError("Document not found.")

        existing = self.classification_repository.list_by_document_id(document_id)

        if existing and not force:
            return existing

        if document.status not in {
            DocumentStatus.CLAUSES_SEGMENTED,
            DocumentStatus.CLASSIFIED,
            DocumentStatus.RISK_SCORED,
            DocumentStatus.EXPLAINED,
        }:
            raise DocumentNotReadyForClassificationError(
                "Document must have CLAUSES_SEGMENTED or CLASSIFIED status before classification."
            )

        clauses = self.clause_repository.list_by_document_id(document_id)

        if not clauses:
            raise DocumentNotReadyForClassificationError(
                "No clauses found for document segmentation."
            )

        if existing and force:
            self.classification_repository.delete_by_document_id(document_id)

        batch_size = settings.GEMINI_CLASSIFICATION_BATCH_SIZE
        clause_payloads = [
            {
                "clause_id": clause.clause_id,
                "heading": clause.heading or "",
                "text": clause.text,
            }
            for clause in clauses
        ]

        clause_by_id = {c.clause_id: c for c in clauses}
        all_results = []

        for i in range(0, len(clause_payloads), batch_size):
            batch = clause_payloads[i : i + batch_size]
            try:
                results = self.classifier.classify_batch(batch)
            except Exception as e:
                logger.warning(f"Classification batch failed, using fallback: {e}")
                results = [
                    ClassificationResult(
                        clause_id=c["clause_id"],
                        category=ClauseCategory.OTHER,
                        raw_response={"fallback": True, "reason": str(e)},
                    )
                    for c in batch
                ]
            all_results.extend(results)

        classifications = [
            ClauseClassification(
                document_id=document.id,
                clause_pk=clause_by_id[res.clause_id].id,
                clause_id=res.clause_id,
                category=res.category,
                model_version=self.classifier.model_name,
                raw_response=res.raw_response,
                source_start=clause_by_id[res.clause_id].source_start,
                source_end=clause_by_id[res.clause_id].source_end,
            )
            for res in all_results
        ]

        self.classification_repository.create_many(classifications)
        if document.status in {
            DocumentStatus.CLAUSES_SEGMENTED,
            DocumentStatus.OCR_COMPLETE,
            DocumentStatus.QUEUED,
        }:
            document.status = DocumentStatus.CLASSIFIED
        self.db.commit()

        logger.info(
            "Clause classification completed",
            extra={
                "_event": "classification_completed",
                "_document_id": document.id,
                "_count": len(classifications),
            },
        )

        return classifications

    def list_classifications(self, document_id: str) -> list[ClauseClassification]:
        document = self.document_repository.get_by_id(document_id)
        if not document:
            from app.services.ocr_service import DocumentNotFoundError

            raise DocumentNotFoundError("Document not found.")

        return self.classification_repository.list_by_document_id(document_id)

    def get_clause_classification(
        self,
        document_id: str,
        clause_id: str,
    ) -> ClauseClassification:
        res = self.classification_repository.get_by_clause_id(document_id, clause_id)
        if not res:
            res = self.classification_repository.get_by_clause_pk(clause_id)
        if not res:
            raise ClassificationNotFoundError(
                f"Classification for clause '{clause_id}' in document '{document_id}' not found."
            )
        return res
