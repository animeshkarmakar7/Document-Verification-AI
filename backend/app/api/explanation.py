from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.explanation import ClauseExplanationResponse, ReadabilityReportResponse
from app.services.explanation_service import (
    DocumentNotFoundError,
    ExplanationService,
    ExplanationServiceError,
    InvalidDocumentStatusError,
)

router = APIRouter(tags=["explanations"])


@router.post(
    "/documents/{document_id}/explain",
    response_model=list[ClauseExplanationResponse],
    status_code=status.HTTP_200_OK,
)
def explain_document(
    document_id: str,
    force: Annotated[bool, Query(description="Force re-explanation if already explained")] = False,
    db: Session = Depends(get_db),
):
    try:
        service = ExplanationService(db=db)
        return service.explain_document(document_id=document_id, force=force)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except InvalidDocumentStatusError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except ExplanationServiceError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get(
    "/documents/{document_id}/explanations",
    response_model=list[ClauseExplanationResponse],
    status_code=status.HTTP_200_OK,
)
def list_explanations(
    document_id: str,
    db: Session = Depends(get_db),
):
    try:
        service = ExplanationService(db=db)
        doc = service.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")
        return service.expl_repo.list_by_document(document_id)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get(
    "/documents/{document_id}/readability-report",
    response_model=ReadabilityReportResponse,
    status_code=status.HTTP_200_OK,
)
def get_readability_report(
    document_id: str,
    db: Session = Depends(get_db),
):
    try:
        service = ExplanationService(db=db)
        return service.get_readability_report(document_id=document_id)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ExplanationServiceError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get(
    "/clauses/{clause_id}/explanation",
    response_model=ClauseExplanationResponse,
    status_code=status.HTTP_200_OK,
)
def get_clause_explanation(
    clause_id: str,
    db: Session = Depends(get_db),
):
    service = ExplanationService(db=db)
    expl = service.get_clause_explanation(clause_id=clause_id)
    if not expl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Explanation for clause '{clause_id}' not found",
        )
    return expl
