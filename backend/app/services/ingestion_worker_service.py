import logging
from dataclasses import dataclass

from app.repositories.clause_repository import ClauseRepository
from app.services.classification_service import ClauseClassificationService
from app.services.clause_service import ClauseSegmentationService
from app.services.explanation_service import ExplanationService
from app.services.ocr_service import OCRService
from app.services.risk_service import RiskService
from app.services.vector_store_service import VectorStoreService
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionWorkerResult:
    document_id: str
    processing_pool: str
    clause_count: int
    indexed_chunk_count: int
    status: str


class IngestionWorkerService:
    """
    Runs the document ingestion pipeline outside the API request path.

    Production deployments should run separate worker processes for CPU and GPU
    queues. CPU workers handle native-text PDFs/DOCX parsing. GPU workers handle
    scanned PDFs/images via OCR or VLM providers before converging on the same
    segmentation, embedding, and analysis stages.
    """

    def __init__(
        self,
        db: Session,
        vector_store: VectorStoreService | None = None,
    ):
        self.db = db
        self.vector_store = vector_store or VectorStoreService()

    def process_document(
        self,
        document_id: str,
        processing_pool: str = "cpu",
    ) -> IngestionWorkerResult:
        logger.info(
            "Document ingestion worker started",
            extra={
                "_event": "ingestion_worker_started",
                "_document_id": document_id,
                "_processing_pool": processing_pool,
            },
        )

        OCRService(self.db).process_document(document_id)
        clauses = ClauseSegmentationService(self.db).segment_document(document_id)

        indexed_count = self.vector_store.index_document_clauses(
            document_id=document_id,
            clauses=clauses,
        )

        ClauseClassificationService(self.db).classify_document(document_id)
        RiskService(self.db).score_document_risk(document_id)
        ExplanationService(self.db).explain_document(document_id)

        final_clauses = ClauseRepository(self.db).list_by_document(document_id)

        logger.info(
            "Document ingestion worker completed",
            extra={
                "_event": "ingestion_worker_completed",
                "_document_id": document_id,
                "_processing_pool": processing_pool,
                "_clause_count": len(final_clauses),
                "_indexed_chunk_count": indexed_count,
            },
        )

        return IngestionWorkerResult(
            document_id=document_id,
            processing_pool=processing_pool,
            clause_count=len(final_clauses),
            indexed_chunk_count=indexed_count,
            status="EXPLAINED",
        )
