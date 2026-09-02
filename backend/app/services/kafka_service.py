import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)


class KafkaPublishError(Exception):
    pass


@dataclass(frozen=True)
class IngestionJobPayload:
    document_id: str
    object_key: str
    filename: str
    content_type: str
    file_size: int
    sha256: str
    processing_pool: str = "cpu"
    queued_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KafkaEventPublisher:
    def __init__(self, bootstrap_servers: str | None = None):
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS

    def publish(
        self,
        topic: str,
        key: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            from kafka import KafkaProducer
        except ImportError as exc:
            raise KafkaPublishError("kafka-python is required for Kafka publishing.") from exc

        producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            key_serializer=lambda value: value.encode("utf-8"),
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            acks="all",
            retries=5,
            linger_ms=10,
        )
        try:
            future = producer.send(topic, key=key, value=payload)
            future.get(timeout=30)
            producer.flush()
        except Exception as exc:
            raise KafkaPublishError(f"Kafka publish failed for topic '{topic}': {exc}") from exc
        finally:
            producer.close()
