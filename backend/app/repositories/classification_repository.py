from app.models.classification import ClauseClassification
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


class ClassificationRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_by_document_id(
        self,
        document_id: str,
    ) -> list[ClauseClassification]:
        statement = (
            select(ClauseClassification)
            .where(ClauseClassification.document_id == document_id)
            .order_by(ClauseClassification.clause_id)
        )
        return list(self.db.scalars(statement).all())

    def get_by_clause_id(
        self,
        document_id: str,
        clause_id: str,
    ) -> ClauseClassification | None:
        statement = select(ClauseClassification).where(
            ClauseClassification.document_id == document_id,
            ClauseClassification.clause_id == clause_id,
        )
        return self.db.scalar(statement)

    def get_by_clause_pk(
        self,
        clause_pk: str,
    ) -> ClauseClassification | None:
        statement = select(ClauseClassification).where(
            ClauseClassification.clause_pk == clause_pk,
        )
        return self.db.scalar(statement)

    def create_many(
        self,
        classifications: list[ClauseClassification],
    ) -> list[ClauseClassification]:
        self.db.add_all(classifications)
        self.db.flush()
        return classifications

    def delete_by_document_id(
        self,
        document_id: str,
    ) -> None:
        statement = delete(ClauseClassification).where(
            ClauseClassification.document_id == document_id
        )
        self.db.execute(statement)
