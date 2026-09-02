from datetime import UTC, datetime

from app.models.ingestion import IngestionJob, OutboxEvent, PageShardStatus
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class IngestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_job(self, job: IngestionJob) -> IngestionJob:
        self.db.add(job)
        self.db.flush()
        return job

    def get_job_by_document_id(self, document_id: str) -> IngestionJob | None:
        return self.db.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
        )

    def create_shards(self, shards: list[PageShardStatus]) -> list[PageShardStatus]:
        self.db.add_all(shards)
        self.db.flush()
        return shards

    def list_shards(self, document_id: str) -> list[PageShardStatus]:
        return list(
            self.db.scalars(
                select(PageShardStatus)
                .where(PageShardStatus.document_id == document_id)
                .order_by(PageShardStatus.shard_index)
            ).all()
        )

    def get_shard(self, document_id: str, shard_index: int) -> PageShardStatus | None:
        return self.db.scalar(
            select(PageShardStatus).where(
                PageShardStatus.document_id == document_id,
                PageShardStatus.shard_index == shard_index,
            )
        )

    def count_shards_by_status(self, job_id: str, status: str) -> int:
        return self.db.scalar(
            select(func.count()).where(
                PageShardStatus.job_id == job_id,
                PageShardStatus.status == status,
            )
        ) or 0

    def create_outbox_event(self, event: OutboxEvent) -> OutboxEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def mark_outbox_published(self, event: OutboxEvent) -> None:
        event.status = "published"
        event.published_at = datetime.now(UTC)
