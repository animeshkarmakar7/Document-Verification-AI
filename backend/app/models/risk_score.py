import uuid
from datetime import datetime

from app.database.base import Base
from app.models.enums import RiskLevel
from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class ClauseRiskScore(Base):

    __tablename__ = "clause_risk_scores"

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

    risk_level: Mapped[RiskLevel] = mapped_column(
        SQLEnum(RiskLevel, name="risk_level"),
        nullable=False,
    )

    risk_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    similarity_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    raw_response: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
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
