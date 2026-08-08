from datetime import datetime

from pydantic import BaseModel, computed_field


class ClauseResponse(BaseModel):
    clause_id: str
    order_index: int
    heading: str | None
    text: str
    source_text_span: dict[str, int]
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def char_count(self) -> int:
        """Total character count of the clause text."""
        return len(self.text)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def word_count(self) -> int:
        """Approximate word count of the clause text."""
        return len(self.text.split())


class ClauseListResponse(BaseModel):
    document_id: str
    total: int
    limit: int | None
    offset: int
    clauses: list[ClauseResponse]


# Kept for backward-compatibility with existing callers.
class ClauseSegmentationResponse(BaseModel):
    document_id: str
    clause_count: int
    clauses: list[ClauseResponse]
