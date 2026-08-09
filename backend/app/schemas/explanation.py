from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ClauseExplanationResponse(BaseModel):
    clause_id: str
    clause_pk: str
    plain_summary: str
    source_span_start: int
    source_span_end: int
    readability_score_original: float | None
    readability_score_summary: float | None
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_grounded: bool
    model_version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReadabilityClauseDetail(BaseModel):
    clause_id: str
    plain_summary: str
    source_span_start: int
    source_span_end: int
    readability_score_original: float | None
    readability_score_summary: float | None
    confidence: float
    is_grounded: bool


class ReadabilityReportResponse(BaseModel):
    document_id: str
    total_clauses: int
    average_original_grade: float | None
    average_summary_grade: float | None
    average_improvement: float | None
    grounded_count: int
    ungrounded_count: int
    clauses: list[ReadabilityClauseDetail]
