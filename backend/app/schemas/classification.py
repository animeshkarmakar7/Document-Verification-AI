from datetime import datetime
from pydantic import BaseModel
from app.models.enums import ClauseCategory


class ClassificationResponse(BaseModel):
    clause_id: str
    category: ClauseCategory
    source_text_span: dict[str, int]
    model_version: str
    created_at: datetime


class ClassificationListResponse(BaseModel):
    document_id: str
    total: int
    classifications: list[ClassificationResponse]


class ClassificationJobResponse(BaseModel):
    document_id: str
    classified_count: int
    classifications: list[ClassificationResponse]
