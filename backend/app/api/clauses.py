from typing import Annotated

from app.api.dependencies import get_db
from app.models.clause import Clause
from app.schemas.clause import (
    ClauseListResponse,
    ClauseResponse,
    ClauseSegmentationResponse,
)
from app.services.clause_service import (
    ClauseNotFoundError,
    ClauseSegmentationService,
    DocumentNotReadyForSegmentationError,
)
from app.services.ocr_service import DocumentNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/documents",
    tags=["Clauses"],
)


@router.post(
    "/{document_id}/clauses/segment",
    response_model=ClauseSegmentationResponse,
    status_code=status.HTTP_200_OK,
    summary="Segment OCR text into legal clauses",
    description=(
        "Splits OCR text on structural legal boundaries such as numbered "
        "sections, clauses, articles, and lettered sub-clauses. Each clause "
        "includes a stable clause_id and source text span."
    ),
)
def segment_clauses(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    force: Annotated[
        bool,
        Query(
            description=(
                "Rebuild existing clauses for this document when true."
            )
        ),
    ] = False,
):
    service = ClauseSegmentationService(db)

    try:
        clauses = service.segment_document(
            document_id=document_id,
            force=force,
        )

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except DocumentNotReadyForSegmentationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ClauseSegmentationResponse(
        document_id=document_id,
        clause_count=len(clauses),
        clauses=[_to_response(clause) for clause in clauses],
    )


@router.get(
    "/{document_id}/clauses",
    response_model=ClauseListResponse,
    summary="List segmented clauses (paginated)",
    description=(
        "Returns clauses for the given document ordered by position. "
        "Use ``limit`` and ``offset`` for pagination. "
        "The ``total`` field always reflects the full unpaged count."
    ),
)
def list_clauses(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=500,
            description="Maximum number of clauses to return.",
        ),
    ] = None,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of clauses to skip before returning results.",
        ),
    ] = 0,
):
    service = ClauseSegmentationService(db)

    try:
        clauses, total = service.list_clauses_paginated(
            document_id,
            limit=limit,
            offset=offset,
        )

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return ClauseListResponse(
        document_id=document_id,
        total=total,
        limit=limit,
        offset=offset,
        clauses=[_to_response(clause) for clause in clauses],
    )


@router.get(
    "/{document_id}/clauses/{clause_id}",
    response_model=ClauseResponse,
    summary="Fetch a single segmented clause",
    description=(
        "Returns the clause identified by ``clause_id`` "
        "(e.g. ``{document_id}-clause-0001``) within the given document."
    ),
)
def get_clause(
    document_id: str,
    clause_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    service = ClauseSegmentationService(db)

    try:
        clause = service.get_clause(document_id, clause_id)

    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ClauseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return _to_response(clause)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(
    clause: Clause,
) -> ClauseResponse:

    return ClauseResponse(
        clause_id=clause.clause_id,
        order_index=clause.order_index,
        heading=clause.heading,
        text=clause.text,
        source_text_span={
            "start": clause.source_start,
            "end": clause.source_end,
        },
        created_at=clause.created_at,
    )
