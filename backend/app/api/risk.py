from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.risk import (
    ClauseRiskResponse,
    RiskDashboardResponse,
)
from app.services.risk_service import (
    DocumentNotFoundError,
    InvalidDocumentStatusError,
    RiskService,
    RiskServiceError,
)

router = APIRouter(tags=["risk"])


@router.post(
    "/documents/{document_id}/score-risk",
    response_model=list[ClauseRiskResponse],
    status_code=status.HTTP_200_OK,
)
def score_document_risk(
    document_id: str,
    force: Annotated[bool, Query(description="Force re-scoring if already scored")] = False,
    db: Session = Depends(get_db),
):
    try:
        service = RiskService(db=db)
        return service.score_document_risk(document_id=document_id, force=force)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except InvalidDocumentStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e
    except RiskServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


@router.get(
    "/documents/{document_id}/risk-dashboard",
    response_model=RiskDashboardResponse,
    status_code=status.HTTP_200_OK,
)
def get_risk_dashboard(
    document_id: str,
    db: Session = Depends(get_db),
):
    try:
        service = RiskService(db=db)
        return service.get_risk_dashboard(document_id=document_id)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except InvalidDocumentStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e
    except RiskServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


@router.get(
    "/clauses/{clause_id}/risk",
    response_model=ClauseRiskResponse,
    status_code=status.HTTP_200_OK,
)
def get_clause_risk(
    clause_id: str,
    db: Session = Depends(get_db),
):
    service = RiskService(db=db)
    risk = service.get_clause_risk(clause_id=clause_id)
    if not risk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk evaluation for clause '{clause_id}' not found",
        )
    return risk
