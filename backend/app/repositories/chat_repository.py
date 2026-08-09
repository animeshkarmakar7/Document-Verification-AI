from app.models.chat import ChatMessage
from sqlalchemy import select
from sqlalchemy.orm import Session


class ChatRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_by_document(self, document_id: str) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.document_id == document_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def create(self, message: ChatMessage) -> ChatMessage:
        self.db.add(message)
        self.db.flush()
        return message
