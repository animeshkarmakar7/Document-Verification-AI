import uuid
from datetime import datetime

from app.database.base import Base
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ClauseExplanation(Base):
    __tablename__ = "clause_explanations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    clause_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    clause_pk: Mapped[str] = mapped_column(
        String, ForeignKey("clauses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plain_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    readability_score_original: Mapped[float | None] = mapped_column(Float, nullable=True)
    readability_score_summary: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
