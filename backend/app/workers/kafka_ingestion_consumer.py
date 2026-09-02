import argparse
import json
import logging
from typing import Any

from app.config.settings import settings
from app.database.database import SessionLocal
from app.models.ingestion import OutboxEvent
from app.repositories.ingestion_repository import IngestionRepository
from app.services.kafka_service import KafkaEventPublisher
from app.services.pdf_sharding_service import PdfShardingService
from app.workers.tasks import process_page_shard

logger = logging.getLogger(__name__)
logging.basicConfig(level=settings.LOG_LEVEL)


def iter_kafka_events(topic: str, group_id: str):
    from kafka import KafkaConsumer

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        enable_auto_commit=False,
        key_deserializer=lambda value: value.decode("utf-8") if value else "",
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        auto_offset_reset="earliest",
    )

    for message in consumer:
        yield consumer, message


def handle_document_ingest_requested(payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        repo = IngestionRepository(db)
        job = repo.get_job_by_document_id(payload["document_id"])
        if job is None:
            raise ValueError(f"Ingestion job missing for document '{payload['document_id']}'")

        plan = PdfShardingService(db).create_shard_plan(
            job=job,
            object_key=payload["object_key"],
        )

        publisher = KafkaEventPublisher()
        for shard in plan.shards:
            shard_payload = {
                "job_id": job.id,
                "document_id": job.document_id,
                "object_key": job.object_key,
                "shard_index": shard.shard_index,
                "page_start": shard.page_start,
                "page_end": shard.page_end,
                "page_count": plan.page_count,
            }
            event = repo.create_outbox_event(
                OutboxEvent(
                    topic=settings.KAFKA_PAGE_SHARDS_TOPIC,
                    aggregate_id=job.document_id,
                    event_type="PdfPageShardCreated",
                    payload=shard_payload,
                )
            )
            db.commit()
            publisher.publish(
                topic=settings.KAFKA_PAGE_SHARDS_TOPIC,
                key=job.document_id,
                payload=shard_payload,
            )
            repo.mark_outbox_published(event)
            db.commit()
            process_page_shard.apply_async(
                args=[job.document_id, shard.shard_index],
                queue=job.processing_pool,
            )

    except Exception:
        db.rollback()
        logger.exception(
            "Kafka ingestion event failed",
            extra={
                "_event": "kafka_ingestion_event_failed",
                "_document_id": payload.get("document_id"),
            },
        )
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Kafka document ingestion consumer")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    for consumer, message in iter_kafka_events(
        settings.KAFKA_DOCUMENT_INGEST_TOPIC,
        group_id="legaldocai-ingestion-service",
    ):
        handle_document_ingest_requested(message.value)
        consumer.commit()
        if args.once:
            break


if __name__ == "__main__":
    main()
