from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RiskFlagType, RiskLevel


class ClauseRiskResponse(BaseModel):
    clause_id: str
    clause_pk: str
    risk_level: RiskLevel
    risk_score: float
    risk_reason: str
    flag_type: RiskFlagType
    suggested_mitigation: str | None = None
    section_heading: str | None = None
    page_number: int = 1
    plain_summary: str | None = None
    risk_category: str = "OPERATIONAL"
    verbatim_text: str = ""
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ScoreRiskRequest(BaseModel):
    force: bool = False


class HighRiskClauseDetail(BaseModel):
    clause_id: str
    category: str
    risk_level: str
    risk_score: float
    risk_reason: str
    flag_type: str
    suggested_mitigation: str | None = None
    section_heading: str | None = None
    page_number: int = 1
    plain_summary: str | None = None
    risk_category: str = "OPERATIONAL"
    verbatim_text: str = ""


class RiskDashboardResponse(BaseModel):
    document_id: str
    overall_risk_score: int = Field(..., ge=0, le=100)
    total_clauses: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    category_breakdown: dict[str, dict[str, int]]
    high_risk_clauses: list[HighRiskClauseDetail]
    clauses: list[ClauseRiskResponse]

