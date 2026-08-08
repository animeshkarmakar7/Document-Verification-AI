from typing import Annotated

from app.api.dependencies import get_db
from app.schemas.document import (
    DocumentUploadResponse,
)
from app.services.upload_service import (
    DuplicateDocumentError,
    UploadService,
)
from app.services.validation_service import (
    FileValidationError,
)
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a legal document",
    description=(
        "Validates a PDF, DOCX, or supported image, calculates its SHA-256 "
        "checksum, stores the raw object in MinIO, persists metadata in "
        "PostgreSQL, and returns an OCR-ready document_id."
    ),
    responses={
        400: {
            "description": "Invalid file upload",
        },
        409: {
            "description": "Duplicate document checksum",
        },
        500: {
            "description": "Unexpected server error",
        },
    },
)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
):

    service = UploadService(db)

    try:

        document = await service.upload(file)

    except FileValidationError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except DuplicateDocumentError as exc:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return DocumentUploadResponse(
        document_id=document.id,
        original_filename=(
            document.original_filename
        ),
        status=document.status,
        storage_uri=document.storage_uri,
        object_key=document.object_key,
        file_size=document.file_size,
        sha256=document.sha256,
        checksum_algorithm=document.checksum_algorithm,
        created_at=document.created_at,
    )
