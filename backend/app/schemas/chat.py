from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=3, ge=1, le=10)


class CitationSchema(BaseModel):
    clause_id: str
    source_span_start: int
    source_span_end: int
    quoted_text: str


class ChatResponse(BaseModel):
    message_id: str
    document_id: str
    query: str
    answer: str
    citations: list[CitationSchema]
    confidence: float
    created_at: datetime


class ChatMessageResponse(BaseModel):
    id: str
    document_id: str
    role: str
    content: str
    citations: list[dict] | list[CitationSchema] | None
    confidence: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatHistoryResponse(BaseModel):
    document_id: str
    total_messages: int
    messages: list[ChatMessageResponse]
