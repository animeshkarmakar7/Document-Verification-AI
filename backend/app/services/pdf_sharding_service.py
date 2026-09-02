import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.config.settings import settings
from app.models.ingestion import IngestionJob, PageShardStatus
from app.repositories.ingestion_repository import IngestionRepository
from app.storage.storage_service import StorageService
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class PdfShardPlan:
    page_count: int
    shard_size: int
    total_shards: int
    metadata: dict
    shards: list[PageShardStatus]


class PdfShardingService:
    def __init__(self, db: Session, storage_service: StorageService | None = None):
        self.db = db
        self.storage_service = storage_service or StorageService()
        self.repo = IngestionRepository(db)

    def create_shard_plan(
        self,
        job: IngestionJob,
        object_key: str,
        shard_size: int | None = None,
    ) -> PdfShardPlan:
        shard_size = shard_size or settings.PDF_SHARD_SIZE_PAGES

        with NamedTemporaryFile(suffix=Path(object_key).suffix or ".pdf", delete=True) as temp_file:
            self.storage_service.download_file_to_path(object_key, temp_file.name)
            metadata = self._extract_metadata(temp_file.name)

        page_count = int(metadata["page_count"])
        total_shards = math.ceil(page_count / shard_size)
        shards = []

        for shard_index in range(total_shards):
            page_start = (shard_index * shard_size) + 1
            page_end = min(page_start + shard_size - 1, page_count)
            shards.append(
                PageShardStatus(
                    document_id=job.document_id,
                    job_id=job.id,
                    shard_index=shard_index,
                    page_start=page_start,
                    page_end=page_end,
                    status="queued",
                )
            )

        self.repo.create_shards(shards)
        job.page_count = page_count
        job.total_shards = total_shards
        job.status = "sharded"
        job.metadata_json = metadata
        self.db.commit()

        return PdfShardPlan(
            page_count=page_count,
            shard_size=shard_size,
            total_shards=total_shards,
            metadata=metadata,
            shards=shards,
        )

    def _extract_metadata(self, file_path: str) -> dict:
        import fitz

        doc = fitz.open(file_path)
        try:
            raw_metadata = doc.metadata or {}
            return {
                "title": raw_metadata.get("title") or "",
                "author": raw_metadata.get("author") or "",
                "subject": raw_metadata.get("subject") or "",
                "creator": raw_metadata.get("creator") or "",
                "producer": raw_metadata.get("producer") or "",
                "page_count": doc.page_count,
                "file_sha256": self._file_hash(file_path),
            }
        finally:
            doc.close()

    def _file_hash(self, file_path: str) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
