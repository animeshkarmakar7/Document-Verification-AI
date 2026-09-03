from app.models.chat import ChatMessage
from app.models.clause import Clause
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.ingestion import IngestionJob
from app.repositories.chat_repository import ChatRepository
from app.repositories.clause_repository import ClauseRepository
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.explanation_repository import ExplanationRepository
from app.services.explanation_service import ExplanationService
from app.services.rag_service import RAGService
from app.services.risk_service import RiskService
from app.services.vector_store_service import VectorSearchResult
from sqlalchemy.orm import Session


class QueryNotFoundError(Exception):
    pass


class DocumentQueryHandler:
    def __init__(self, db: Session):
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.chat_repo = ChatRepository(db)
        self.classification_repo = ClassificationRepository(db)
        self.explanation_repo = ExplanationRepository(db)

    def get_document(self, document_id: str) -> Document:
        document = self.document_repo.get_by_id(document_id)
        if document is None:
            raise QueryNotFoundError(f"Document '{document_id}' not found")
        return document

    def list_clauses(
        self,
        document_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Clause], int]:
        self.get_document(document_id)
        total = self.clause_repo.count_by_document_id(document_id)
        clauses = self.clause_repo.list_by_document_id(
            document_id=document_id,
            limit=limit,
            offset=offset,
        )
        return clauses, total

    def list_chat_history(self, document_id: str) -> list[ChatMessage]:
        self.get_document(document_id)
        return self.chat_repo.list_by_document(document_id)

    def list_classifications(self, document_id: str):
        self.get_document(document_id)
        return self.classification_repo.list_by_document_id(document_id)

    def get_risk_dashboard(self, document_id: str) -> dict:
        self.get_document(document_id)
        return RiskService(db=self.db).get_risk_dashboard(document_id)

    def list_explanations(self, document_id: str):
        self.get_document(document_id)
        return self.explanation_repo.list_by_document(document_id)

    def get_document_summary(self, document_id: str) -> dict:
        self.get_document(document_id)
        return ExplanationService(db=self.db).get_document_summary(document_id)

    def search_document(
        self,
        document_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        self.get_document(document_id)
        clauses = self.clause_repo.list_by_document(document_id)
        return RAGService(db=self.db).vector_store.hybrid_search(
            document_id=document_id,
            query=query,
            clauses=clauses,
            top_k=top_k,
        )

    def get_pipeline_status(self, document_id: str) -> dict:
        document = self.get_document(document_id)
        clauses = self.clause_repo.list_by_document(document_id)
        clause_count = len(clauses)

        STAGE_MAP = {
            DocumentStatus.QUEUED: ("Queued for Ingestion", 10),
            DocumentStatus.OCR_COMPLETE: ("OCR & Text Extracted", 30),
            DocumentStatus.CLAUSES_SEGMENTED: ("Provisions Segmented", 50),
            DocumentStatus.CLASSIFIED: ("Provisions Classified", 70),
            DocumentStatus.RISK_SCORED: ("Risk Scored", 85),
            DocumentStatus.EXPLAINED: ("Analysis Complete", 100),
            DocumentStatus.FAILED: ("Processing Failed", 100),
        }

        stage_name, progress = STAGE_MAP.get(document.status, ("Processing", 20))
        is_complete = document.status == DocumentStatus.EXPLAINED
        is_failed = document.status == DocumentStatus.FAILED

        job = self.db.query(IngestionJob).filter(IngestionJob.document_id == document_id).first()
        page_count = job.page_count if job else None

        return {
            "document_id": document.id,
            "status": document.status,
            "stage": stage_name,
            "progress_percent": progress,
            "clause_count": clause_count,
            "page_count": page_count,
            "error_message": getattr(document, "error_message", None),
            "is_complete": is_complete,
            "is_failed": is_failed,
        }
