from typing import Annotated

from app.api.dependencies import get_db
from app.cqrs.queries import DocumentQueryHandler, QueryNotFoundError
from app.models.classification import ClauseClassification
from app.schemas.chat import ChatHistoryResponse
from app.schemas.classification import ClassificationListResponse, ClassificationResponse
from app.schemas.clause import ClauseListResponse, ClauseResponse
from app.schemas.explanation import ClauseExplanationResponse
from app.schemas.ingestion import DocumentStatusResponse, PipelineStatusResponse
from app.schemas.risk import RiskDashboardResponse
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/queries", tags=["Queries"])


class SearchResultResponse(BaseModel):
    clause_id: str
    text: str
    score: float
    source_start: int
    source_end: int
    heading: str | None = None
    chunk_id: str | None = None


class DocumentSearchResponse(BaseModel):
    document_id: str
    query: str
    results: list[SearchResultResponse]


def _clause_response(clause) -> ClauseResponse:
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


@router.get(
    "/documents/{document_id}",
    response_model=DocumentStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_document_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentQueryHandler(db=db)

    try:
        document = handler.get_document(document_id)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return DocumentStatusResponse(
        document_id=document.id,
        status=document.status,
        original_filename=document.original_filename,
        object_key=document.object_key,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get(
    "/documents/{document_id}/pipeline-status",
    response_model=PipelineStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_pipeline_status_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentQueryHandler(db=db)

    try:
        return handler.get_pipeline_status(document_id)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/documents/{document_id}/clauses",
    response_model=ClauseListResponse,
    status_code=status.HTTP_200_OK,
)
def list_document_clauses_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int | None, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    handler = DocumentQueryHandler(db=db)

    try:
        clauses, total = handler.list_clauses(
            document_id=document_id,
            limit=limit,
            offset=offset,
        )
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ClauseListResponse(
        document_id=document_id,
        total=total,
        limit=limit,
        offset=offset,
        clauses=[_clause_response(clause) for clause in clauses],
    )


@router.get(
    "/documents/{document_id}/chat-history",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
)
def get_chat_history_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentQueryHandler(db=db)

    try:
        messages = handler.list_chat_history(document_id)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {
        "document_id": document_id,
        "total_messages": len(messages),
        "messages": messages,
    }


@router.get(
    "/documents/{document_id}/classifications",
    response_model=ClassificationListResponse,
    status_code=status.HTTP_200_OK,
)
def list_classifications_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentQueryHandler(db=db)

    try:
        classifications = handler.list_classifications(document_id)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ClassificationListResponse(
        document_id=document_id,
        total=len(classifications),
        classifications=[
            _classification_response(classification)
            for classification in classifications
        ],
    )


@router.get(
    "/documents/{document_id}/risk-dashboard",
    response_model=RiskDashboardResponse,
    status_code=status.HTTP_200_OK,
)
def get_risk_dashboard_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentQueryHandler(db=db)

    try:
        return handler.get_risk_dashboard(document_id)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/documents/{document_id}/explanations",
    response_model=list[ClauseExplanationResponse],
    status_code=status.HTTP_200_OK,
)
def list_explanations_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentQueryHandler(db=db)

    try:
        return handler.list_explanations(document_id)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/documents/{document_id}/summary",
    status_code=status.HTTP_200_OK,
)
def get_document_summary_query(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentQueryHandler(db=db)

    try:
        return handler.get_document_summary(document_id)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/documents/{document_id}/search",
    response_model=DocumentSearchResponse,
    status_code=status.HTTP_200_OK,
)
def search_document_query(
    document_id: str,
    query: Annotated[str, Query(min_length=2)],
    db: Annotated[Session, Depends(get_db)],
    top_k: Annotated[int, Query(ge=1, le=20)] = 5,
):
    handler = DocumentQueryHandler(db=db)

    try:
        results = handler.search_document(document_id, query=query, top_k=top_k)
    except QueryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return DocumentSearchResponse(
        document_id=document_id,
        query=query,
        results=[SearchResultResponse(**result.__dict__) for result in results],
    )


def _classification_response(item: ClauseClassification) -> ClassificationResponse:
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
