from typing import Annotated

from app.api.dependencies import get_db
from app.cqrs.queries import DocumentQueryHandler, QueryNotFoundError
from app.schemas.chat import ChatHistoryResponse
from app.schemas.clause import ClauseListResponse, ClauseResponse
from app.schemas.ingestion import DocumentStatusResponse
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
