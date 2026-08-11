from app.models.risk import ClauseRisk
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


class RiskRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_by_document(self, document_id: str) -> list[ClauseRisk]:
        stmt = (
            select(ClauseRisk)
            .where(ClauseRisk.document_id == document_id)
            .order_by(ClauseRisk.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_by_clause_id(self, clause_id: str) -> ClauseRisk | None:
        stmt = select(ClauseRisk).where(ClauseRisk.clause_id == clause_id)
        return self.db.scalars(stmt).first()

    def get_by_clause_pk(self, clause_pk: str) -> ClauseRisk | None:
        stmt = select(ClauseRisk).where(ClauseRisk.clause_pk == clause_pk)
        return self.db.scalars(stmt).first()

    def create_many(self, risks: list[ClauseRisk]) -> list[ClauseRisk]:
        self.db.add_all(risks)
        self.db.flush()
        return risks

    def delete_by_document(self, document_id: str) -> int:
        stmt = delete(ClauseRisk).where(ClauseRisk.document_id == document_id)
        result = self.db.execute(stmt)
        return result.rowcount

    def list_by_document_id(self, document_id: str) -> list[ClauseRisk]:
        """Alias for list_by_document."""
        return self.list_by_document(document_id)

    def delete_by_document_id(self, document_id: str) -> int:
        """Alias for delete_by_document."""
        return self.delete_by_document(document_id)
