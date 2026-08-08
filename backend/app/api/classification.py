from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models.classification import ClauseClassification
from app.schemas.classification import (
    ClassificationJobResponse,
    ClassificationListResponse,
    ClassificationResponse,
)
from app.services.classification_service import (
    ClassificationNotFoundError,
    ClauseClassificationService,
    DocumentNotReadyForClassificationError,
)
from app.services.gemini_classifier import ClassificationError
from app.services.ocr_service import DocumentNotFoundError

router = APIRouter(
    prefix="/documents",
    tags=["Classifications"],
)


@router.post(
    "/{document_id}/classify",
    response_model=ClassificationJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Classify clauses using Gemini",
)
def classify_document(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    force: Annotated[
        bool,
        Query(
            description="Re-run classification for this document when true."
        ),
    ] = False,
):
    service = ClauseClassificationService(db)

    try:
        classifications = service.classify_document(
            document_id=document_id,
            force=force,
        )

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except DocumentNotReadyForClassificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ClassificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return ClassificationJobResponse(
        document_id=document_id,
        classified_count=len(classifications),
        classifications=[_to_response(item) for item in classifications],
    )


@router.get(
    "/{document_id}/classifications",
    response_model=ClassificationListResponse,
    summary="List document clause classifications",
)
def list_classifications(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    service = ClauseClassificationService(db)

    try:
        classifications = service.list_classifications(document_id)

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ClassificationListResponse(
        document_id=document_id,
        total=len(classifications),
        classifications=[_to_response(item) for item in classifications],
    )


@router.get(
    "/{document_id}/clauses/{clause_id}/classification",
    response_model=ClassificationResponse,
    summary="Get single clause classification",
)
def get_clause_classification(
    document_id: str,
    clause_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    service = ClauseClassificationService(db)

    try:
        classification = service.get_clause_classification(
            document_id=document_id,
            clause_id=clause_id,
        )

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ClassificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return _to_response(classification)


def _to_response(item: ClauseClassification) -> ClassificationResponse:
    return ClassificationResponse(
        clause_id=item.clause_id,
        category=item.category,
        source_text_span={
            "start": item.source_start,
            "end": item.source_end,
        },
        model_version=item.model_version,
        created_at=item.created_at,
    )
