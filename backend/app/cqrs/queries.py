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
            DocumentStatus.QUEUED: ("Validating & Securely Ingesting Document", 15),
            DocumentStatus.OCR_COMPLETE: ("Extracting & Structuring Document Text", 35),
            DocumentStatus.CLAUSES_SEGMENTED: ("Segmenting Agreement Provisions", 55),
            DocumentStatus.CLASSIFIED: ("Classifying Terms & Legal Context", 70),
            DocumentStatus.RISK_SCORED: ("Analyzing Contractual Risks & Liabilities", 85),
            DocumentStatus.EXPLAINED: ("Analysis Complete", 100),
            DocumentStatus.FAILED: ("Processing Unsuccessful", 100),
        }

        stage_name, progress = STAGE_MAP.get(document.status, ("Analyzing Document Provisions", 25))
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

    def get_suggested_questions(self, document_id: str) -> list[str]:
        doc = self.get_document(document_id)
        clauses = self.clause_repo.list_by_document(document_id)
        
        # Determine contract type / tone from clauses
        all_text = " ".join(c.text.lower() for c in clauses[:10])
        
        if any(w in all_text for w in ["rent", "tenant", "landlord", "lease", "premises"]):
            return [
                "What are the security deposit refund conditions?",
                "What is the required termination notice period and lock-in term?",
                "Are there any penalty fees for late rent payment?",
                "What are the tenant's maintenance and utility responsibilities?",
                "Is subletting or commercial use of the property permitted?",
            ]
        elif any(w in all_text for w in ["confidential", "nda", "proprietary", "disclose"]):
            return [
                "What information is specifically defined as Confidential Information?",
                "What is the duration of the non-disclosure obligation?",
                "What remedies or injunctions are available upon breach?",
                "What are the standard exclusions from confidentiality?",
            ]
        elif any(w in all_text for w in ["employment", "employee", "employer", "salary", "bonus"]):
            return [
                "What are the termination notice and severance provisions?",
                "What non-compete and non-solicitation restrictions apply?",
                "How are bonuses and expense reimbursements handled?",
                "What are the intellectual property ownership assignment terms?",
            ]
        else:
            return [
                "What are the primary financial liabilities and payment terms?",
                "What are the termination conditions and notice requirements?",
                "What are the key liability limitations and indemnification clauses?",
                "What are the core rights and remedies granted under this agreement?",
            ]
