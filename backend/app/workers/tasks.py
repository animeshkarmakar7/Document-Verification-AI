from app.database.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.repositories.ingestion_repository import IngestionRepository
from app.services.page_shard_processor import PageShardProcessor
from app.services.vector_store_service import VectorStoreService
from app.workers.celery_app import celery_app


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
        if job is not None:
            job.completed_shards = ingestion_repo.count_shards_by_status(job.id, "completed")
            if job.completed_shards >= job.total_shards:
                job.status = "indexed"

        db.commit()
        return {
            "document_id": document_id,
            "shard_index": shard_index,
            "indexed_chunk_count": indexed_count,
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
        raise
    finally:
        db.close()
