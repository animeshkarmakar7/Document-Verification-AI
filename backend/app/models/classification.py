import uuid
from datetime import datetime

from app.database.base import Base
from app.models.enums import ClauseCategory
from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class ClauseClassification(Base):

    __tablename__ = "clause_classifications"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    clause_pk: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("clauses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    clause_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    category: Mapped[ClauseCategory] = mapped_column(
        SQLEnum(ClauseCategory, name="clause_category"),
        nullable=False,
    )

    model_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    raw_response: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    source_start: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    source_end: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
