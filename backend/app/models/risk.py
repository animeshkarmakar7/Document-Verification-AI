import uuid
from datetime import datetime

from app.database.base import Base
from app.models.enums import RiskFlagType, RiskLevel
from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column


class ClauseRisk(Base):
    __tablename__ = "clause_risks"

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
    risk_level: Mapped[RiskLevel] = mapped_column(
        SQLEnum(RiskLevel, name="risk_level"), nullable=False, index=True
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_reason: Mapped[str] = mapped_column(Text, nullable=False)
    flag_type: Mapped[RiskFlagType] = mapped_column(
        SQLEnum(RiskFlagType, name="risk_flag_type"), nullable=False
    )
    suggested_mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
