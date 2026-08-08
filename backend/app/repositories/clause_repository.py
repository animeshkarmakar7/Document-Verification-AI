from app.models.clause import Clause
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session


class ClauseRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_by_document_id(
        self,
        document_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Clause]:
        """Return clauses ordered by position, with optional pagination."""

        statement = (
            select(Clause)
            .where(Clause.document_id == document_id)
            .order_by(Clause.order_index)
            .offset(offset)
        )

        if limit is not None:
            statement = statement.limit(limit)

        return list(self.db.scalars(statement).all())

    def count_by_document_id(self, document_id: str) -> int:
        """Return the total number of clauses for a document."""

        statement = select(func.count()).where(
            Clause.document_id == document_id
        )
        return self.db.scalar(statement) or 0

    def get_by_clause_id(
        self,
        document_id: str,
        clause_id: str,
    ) -> Clause | None:
        """Return a single clause by its stable clause_id string."""

        statement = select(Clause).where(
            Clause.document_id == document_id,
            Clause.clause_id == clause_id,
        )
        return self.db.scalar(statement)

    def create_many(
        self,
        clauses: list[Clause],
    ) -> list[Clause]:

        self.db.add_all(clauses)
        self.db.flush()

        return clauses

    def delete_by_document_id(
        self,
        document_id: str,
    ) -> None:

        statement = delete(Clause).where(
            Clause.document_id == document_id
        )
        self.db.execute(statement)
