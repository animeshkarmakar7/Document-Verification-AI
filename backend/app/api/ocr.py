from typing import Annotated

from app.api.dependencies import get_db
from app.schemas.ocr import OCRResponse, OCRStatusResponse
from app.services.ocr_extractor import OCRExtractionError
from app.services.ocr_service import (
    DocumentNotFoundError,
    DocumentNotReadyForOCRError,
    OCRService,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/documents",
    tags=["OCR"],
)


@router.post(
    "/{document_id}/ocr",
    response_model=OCRResponse,
    status_code=status.HTTP_200_OK,
    summary="Run OCR for an uploaded document",
    description=(
        "Downloads the uploaded raw document from MinIO, extracts text and "
        "layout metadata, stores the OCR result in PostgreSQL, and updates "
        "the document status."
    ),
)
def run_ocr(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    service = OCRService(db)

    try:
        ocr_result = service.process_document(document_id)

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except DocumentNotReadyForOCRError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except OCRExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    document, _ = service.get_status(document_id)

    return OCRResponse(
        document_id=ocr_result.document_id,
        status=document.status,
        provider=ocr_result.provider,
        text=ocr_result.text,
        page_count=ocr_result.page_count,
        layout=ocr_result.layout,
        created_at=ocr_result.created_at,
    )


@router.get(
    "/{document_id}/ocr/status",
    response_model=OCRStatusResponse,
    summary="Get OCR status",
)
def get_ocr_status(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    service = OCRService(db)

    try:
        document, has_ocr_result = service.get_status(document_id)

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return OCRStatusResponse(
        document_id=document.id,
        status=document.status,
        has_ocr_result=has_ocr_result,
    )


@router.get(
    "/{document_id}/ocr",
    response_model=OCRResponse,
    summary="Get OCR result",
)
def get_ocr_result(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    service = OCRService(db)

    try:
        ocr_result = service.get_result(document_id)
        document, _ = service.get_status(document_id)

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except DocumentNotReadyForOCRError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return OCRResponse(
        document_id=ocr_result.document_id,
        status=document.status,
        provider=ocr_result.provider,
        text=ocr_result.text,
        page_count=ocr_result.page_count,
        layout=ocr_result.layout,
        created_at=ocr_result.created_at,
    )
