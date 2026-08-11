from app.models.explanation import ClauseExplanation
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


class ExplanationRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_by_document(self, document_id: str) -> list[ClauseExplanation]:
        stmt = (
            select(ClauseExplanation)
            .where(ClauseExplanation.document_id == document_id)
            .order_by(ClauseExplanation.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_by_clause_id(self, clause_id: str) -> ClauseExplanation | None:
        stmt = select(ClauseExplanation).where(ClauseExplanation.clause_id == clause_id)
        return self.db.scalars(stmt).first()

    def get_by_clause_pk(self, clause_pk: str) -> ClauseExplanation | None:
        stmt = select(ClauseExplanation).where(ClauseExplanation.clause_pk == clause_pk)
        return self.db.scalars(stmt).first()

    def create_many(self, explanations: list[ClauseExplanation]) -> list[ClauseExplanation]:
        self.db.add_all(explanations)
        self.db.flush()
        return explanations

    def delete_by_document(self, document_id: str) -> int:
        stmt = delete(ClauseExplanation).where(ClauseExplanation.document_id == document_id)
        result = self.db.execute(stmt)
        return result.rowcount

    def list_by_document_id(self, document_id: str) -> list[ClauseExplanation]:
        """Alias for list_by_document."""
        return self.list_by_document(document_id)

    def delete_by_document_id(self, document_id: str) -> int:
        """Alias for delete_by_document."""
        return self.delete_by_document(document_id)
