from typing import Annotated

from app.api.dependencies import get_db
from app.config.settings import settings
from app.cqrs.commands import CommandValidationError, DocumentCommandHandler
from app.models.classification import ClauseClassification
from app.models.clause import Clause
from app.schemas.document import DocumentUploadResponse
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.classification import ClassificationJobResponse, ClassificationResponse
from app.schemas.clause import ClauseResponse, ClauseSegmentationResponse
from app.schemas.explanation import ClauseExplanationResponse
from app.schemas.ingestion import (
    CompleteDirectUploadRequest,
    IngestionQueuedResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.schemas.risk import ClauseRiskResponse
from app.services.classification_service import DocumentNotReadyForClassificationError
from app.services.clause_service import DocumentNotReadyForSegmentationError
from app.services.explanation_service import (
    DocumentNotFoundError as ExplanationDocumentNotFoundError,
    ExplanationServiceError,
    InvalidDocumentStatusError as ExplanationInvalidStatusError,
)
from app.services.gemini_classifier import ClassificationError
from app.services.ocr_service import DocumentNotFoundError, DocumentNotReadyForOCRError
from app.services.kafka_service import KafkaEventPublisher
from app.services.rag_service import (
    DocumentNotFoundError as RAGDocumentNotFoundError,
    RAGServiceError,
)
from app.services.risk_service import (
    DocumentNotFoundError as RiskDocumentNotFoundError,
    InvalidDocumentStatusError as RiskInvalidStatusError,
    RiskServiceError,
)
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
    handler = DocumentCommandHandler(
        db=db,
        event_publisher=KafkaEventPublisher(),
    )

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
        event_publisher=KafkaEventPublisher(),
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
    except (DocumentNotFoundError, RiskDocumentNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentNotReadyForOCRError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return {
        "document_id": document_id,
        "status": "OCR_COMPLETE",
        "provider": ocr_result.provider,
        "page_count": ocr_result.page_count,
        "queue_name": settings.KAFKA_DOCUMENT_INGEST_TOPIC,
        "processing_pool": "cpu",
    }


@router.post(
    "/documents/{document_id}/clauses/segment",
    response_model=ClauseSegmentationResponse,
    status_code=status.HTTP_200_OK,
)
def segment_clauses_command(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
):
    handler = DocumentCommandHandler(db=db)

    try:
        clauses = handler.segment_document(document_id=document_id, force=force)
    except (DocumentNotFoundError, ExplanationDocumentNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentNotReadyForSegmentationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ClauseSegmentationResponse(
        document_id=document_id,
        clause_count=len(clauses),
        clauses=[_clause_response(clause) for clause in clauses],
    )


@router.post(
    "/documents/{document_id}/classify",
    response_model=ClassificationJobResponse,
    status_code=status.HTTP_200_OK,
)
def classify_document_command(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
):
    handler = DocumentCommandHandler(db=db)

    try:
        classifications = handler.classify_document(document_id=document_id, force=force)
    except (DocumentNotFoundError, RAGDocumentNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentNotReadyForClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ClassificationJobResponse(
        document_id=document_id,
        classified_count=len(classifications),
        classifications=[
            _classification_response(classification)
            for classification in classifications
        ],
    )


@router.post(
    "/documents/{document_id}/score-risk",
    response_model=list[ClauseRiskResponse],
    status_code=status.HTTP_200_OK,
)
def score_document_risk_command(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
):
    handler = DocumentCommandHandler(db=db)

    try:
        return handler.score_document_risk(document_id=document_id, force=force)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RiskInvalidStatusError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RiskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/documents/{document_id}/explain",
    response_model=list[ClauseExplanationResponse],
    status_code=status.HTTP_200_OK,
)
def explain_document_command(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
):
    handler = DocumentCommandHandler(db=db)

    try:
        return handler.explain_document(document_id=document_id, force=force)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ExplanationInvalidStatusError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ExplanationServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/documents/{document_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
def chat_with_document_command(
    document_id: str,
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
):
    handler = DocumentCommandHandler(db=db)

    try:
        return handler.chat_with_document(
            document_id=document_id,
            query=payload.query,
            top_k=payload.top_k,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RAGServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


def _clause_response(clause: Clause) -> ClauseResponse:
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
