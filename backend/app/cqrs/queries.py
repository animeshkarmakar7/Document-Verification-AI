from app.models.chat import ChatMessage
from app.models.clause import Clause
from app.models.document import Document
from app.repositories.chat_repository import ChatRepository
from app.repositories.clause_repository import ClauseRepository
from app.repositories.document_repository import DocumentRepository
from app.services.rag_service import RAGService
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
