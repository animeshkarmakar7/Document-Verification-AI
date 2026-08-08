from app.models.document import Document
from sqlalchemy import select
from sqlalchemy.orm import Session


class DocumentRepository:

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

    def get_by_sha256(
        self,
        sha256: str,
    ) -> Document | None:

        statement = (
            select(Document)
            .where(Document.sha256 == sha256)
        )

        return self.db.scalar(statement)

    def get_by_id(
        self,
        document_id: str,
    ) -> Document | None:

        statement = select(Document).where(
            Document.id == document_id
        )

        return self.db.scalar(statement)

    def create(
        self,
        document: Document,
    ) -> Document:

        self.db.add(document)

        self.db.flush()

        return document
