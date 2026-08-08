from app.models.ocr_result import OCRResult
from sqlalchemy import select
from sqlalchemy.orm import Session


class OCRRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_by_document_id(
        self,
        document_id: str,
    ) -> OCRResult | None:

        statement = select(OCRResult).where(
            OCRResult.document_id == document_id
        )

        return self.db.scalar(statement)

    def create(
        self,
        ocr_result: OCRResult,
    ) -> OCRResult:

        self.db.add(ocr_result)
        self.db.flush()

        return ocr_result
