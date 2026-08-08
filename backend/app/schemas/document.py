from datetime import datetime

from app.models.enums import DocumentStatus
from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):

    document_id: str

    original_filename: str

    status: DocumentStatus

    storage_uri: str

    object_key: str

    file_size: int

    sha256: str

    checksum_algorithm: str

    created_at: datetime
