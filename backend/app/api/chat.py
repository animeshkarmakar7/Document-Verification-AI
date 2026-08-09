from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.chat import ChatHistoryResponse, ChatRequest, ChatResponse
from app.services.rag_service import (
    DocumentNotFoundError,
    RAGService,
    RAGServiceError,
)

router = APIRouter(tags=["chat"])


@router.post(
    "/documents/{document_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
def chat_with_document(
    document_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    try:
        service = RAGService(db=db)
        return service.chat(
            document_id=document_id, query=payload.query, top_k=payload.top_k
        )
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except RAGServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


@router.get(
    "/documents/{document_id}/chat-history",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
)
def get_chat_history(
    document_id: str,
    db: Session = Depends(get_db),
):
    try:
        service = RAGService(db=db)
        messages = service.get_chat_history(document_id=document_id)
        return {
            "document_id": document_id,
            "total_messages": len(messages),
            "messages": messages,
        }
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except RAGServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e
