import logging

from app.database.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.repositories.ingestion_repository import IngestionRepository
from app.services.ingestion_worker_service import IngestionWorkerService
from app.services.kafka_service import KafkaEventPublisher
from app.services.page_shard_processor import PageShardProcessor
from app.services.vector_store_service import VectorStoreService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    name="ingestion.process_page_shard",
)
def process_page_shard(self, document_id: str, shard_index: int) -> dict:
    db = SessionLocal()
    try:
        ingestion_repo = IngestionRepository(db)
        document_repo = DocumentRepository(db)

        document = document_repo.get_by_id(document_id)
        if document is None:
            raise ValueError(f"Document '{document_id}' not found")

        shard = ingestion_repo.get_shard(document_id, shard_index)
        if shard is None:
            raise ValueError(f"Shard {shard_index} not found for document '{document_id}'")

        job = ingestion_repo.get_job_by_document_id(document_id)

        shard.status = "processing"
        db.commit()

        chunks = PageShardProcessor().extract_chunks(
            document_id=document_id,
            object_key=document.object_key,
            shard=shard,
            processing_pool=job.processing_pool if job is not None else "cpu",
        )
        indexed_count = VectorStoreService().index_extracted_chunks(chunks)

        shard.status = "completed"
        if job is None:
            job = ingestion_repo.get_job_by_document_id(document_id)
        
        all_completed = False
        if job is not None:
            job.completed_shards = ingestion_repo.count_shards_by_status(job.id, "completed")
            if job.completed_shards >= job.total_shards:
                job.status = "indexed"
                all_completed = True

        db.commit()

        # If all shards completed, trigger full document analysis pipeline
        if all_completed:
            logger.info(
                "All shards completed for document; dispatching analyze_document",
                extra={"_document_id": document_id},
            )
            analyze_document.delay(document_id)

        return {
            "document_id": document_id,
            "shard_index": shard_index,
            "indexed_chunk_count": indexed_count,
            "all_completed": all_completed,
        }
    except Exception as exc:
        db.rollback()
        ingestion_repo = IngestionRepository(db)
        shard = ingestion_repo.get_shard(document_id, shard_index)
        if shard is not None:
            shard.status = "failed"
            shard.retry_count += 1
            shard.error_message = str(exc)
            job = ingestion_repo.get_job_by_document_id(document_id)
            if job is not None:
                job.failed_shards = ingestion_repo.count_shards_by_status(job.id, "failed")
            db.commit()

            # Publish to DLQ if max retries exceeded or critical failure
            if getattr(self.request, "retries", 0) >= getattr(self, "max_retries", 5):
                try:
                    KafkaEventPublisher().publish_dlq(
                        key=document_id,
                        original_payload={"document_id": document_id, "shard_index": shard_index},
                        error_message=str(exc),
                    )
                except Exception as dlq_err:
                    logger.error(f"Failed to publish to Kafka DLQ: {dlq_err}")

        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="ingestion.analyze_document",
)
def analyze_document(self, document_id: str) -> dict:
    """
    Executes OCR text processing, clause segmentation, classification,
    risk scoring, and explanation generation.
    """
    db = SessionLocal()
    try:
        logger.info(
            "Document analysis started",
            extra={"_event": "analyze_document_started", "_document_id": document_id},
        )
        result = IngestionWorkerService(db=db).process_document(
            document_id=document_id,
            processing_pool="cpu",
            skip_vector_index=True,
        )
        logger.info(
            "Document analysis completed",
            extra={
                "_event": "analyze_document_completed",
                "_document_id": document_id,
                "_clause_count": result.clause_count,
                "_status": result.status,
            },
        )
        return {
            "document_id": document_id,
            "clause_count": result.clause_count,
            "indexed_chunk_count": result.indexed_chunk_count,
            "status": result.status,
        }
    except Exception as exc:
        logger.exception(
            "Document analysis task failed",
            extra={"_event": "analyze_document_failed", "_document_id": document_id},
        )
        try:
            doc = DocumentRepository(db).get_by_id(document_id)
            if doc is not None:
                doc.status = "FAILED"
                doc.error_message = str(exc)[:500]
                db.commit()
        except Exception:
            db.rollback()

        if getattr(self.request, "retries", 0) >= getattr(self, "max_retries", 3):
            try:
                KafkaEventPublisher().publish_dlq(
                    key=document_id,
                    original_payload={"document_id": document_id, "task": "analyze_document"},
                    error_message=str(exc),
                )
            except Exception as dlq_err:
                logger.error(f"Failed to publish analyze_document to Kafka DLQ: {dlq_err}")
        raise
    finally:
        db.close()
