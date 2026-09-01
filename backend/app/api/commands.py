from typing import Annotated

from app.api.dependencies import get_db
from app.config.settings import settings
from app.cqrs.commands import CommandValidationError, DocumentCommandHandler
from app.schemas.document import DocumentUploadResponse
from app.schemas.ingestion import (
    CompleteDirectUploadRequest,
    IngestionQueuedResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.services.ocr_service import DocumentNotFoundError, DocumentNotReadyForOCRError
from app.services.queue_service import get_queue_publisher
from app.services.validation_service import FileValidationError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/commands", tags=["Commands"])


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_document_command(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentCommandHandler(db=db)

    try:
        document = await handler.upload_via_api(file)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return DocumentUploadResponse(
        document_id=document.id,
        original_filename=document.original_filename,
        status=document.status,
        storage_uri=document.storage_uri,
        object_key=document.object_key,
        file_size=document.file_size,
        sha256=document.sha256,
        checksum_algorithm=document.checksum_algorithm,
        created_at=document.created_at,
    )


@router.post(
    "/documents/presigned-upload",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_presigned_upload_command(
    payload: PresignedUploadRequest,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentCommandHandler(db=db)

    try:
        return handler.create_presigned_upload(payload)
    except CommandValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/documents/upload-complete",
    response_model=IngestionQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def complete_direct_upload_command(
    payload: CompleteDirectUploadRequest,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentCommandHandler(
        db=db,
        queue_publisher=get_queue_publisher(),
    )

    try:
        return handler.complete_direct_upload(payload)
    except CommandValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/documents/{document_id}/ingest/text",
    status_code=status.HTTP_202_ACCEPTED,
)
def run_text_ingestion_command(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentCommandHandler(db=db)

    try:
        ocr_result = handler.run_text_ingestion_now(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentNotReadyForOCRError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return {
        "document_id": document_id,
        "status": "OCR_COMPLETE",
        "provider": ocr_result.provider,
        "page_count": ocr_result.page_count,
        "queue_name": settings.INGESTION_QUEUE_NAME,
        "processing_pool": "cpu",
    }
