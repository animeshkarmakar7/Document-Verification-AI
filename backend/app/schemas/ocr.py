from datetime import datetime

from app.models.enums import DocumentStatus
from pydantic import BaseModel


class OCRPage(BaseModel):
    page_number: int
    text: str


class OCRResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    provider: str
    text: str
    page_count: int
    layout: dict
    created_at: datetime


class OCRStatusResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    has_ocr_result: bool
