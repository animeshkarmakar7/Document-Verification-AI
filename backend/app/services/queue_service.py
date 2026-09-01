import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)


class QueuePublishError(Exception):
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


class QueuePublisher:
    def publish(self, queue_name: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError


class InMemoryQueuePublisher(QueuePublisher):
    published: list[tuple[str, dict[str, Any]]] = []

    def publish(self, queue_name: str, payload: dict[str, Any]) -> None:
        self.published.append((queue_name, payload))
        logger.info(
            "Ingestion job recorded in local memory queue",
            extra={
                "_event": "queue_publish_memory",
                "_queue": queue_name,
                "_document_id": payload.get("document_id"),
                "_processing_pool": payload.get("processing_pool"),
            },
        )


class RedisQueuePublisher(QueuePublisher):
    def __init__(self, redis_url: str):
        try:
            import redis
        except ImportError as exc:
            raise QueuePublishError(
                "Redis queue backend selected but redis package is not installed."
            ) from exc

        self.client = redis.Redis.from_url(redis_url)

    def publish(self, queue_name: str, payload: dict[str, Any]) -> None:
        self.client.lpush(queue_name, json.dumps(payload))


class RabbitMQQueuePublisher(QueuePublisher):
    def __init__(self, rabbitmq_url: str):
        try:
            import pika
        except ImportError as exc:
            raise QueuePublishError(
                "RabbitMQ queue backend selected but pika package is not installed."
            ) from exc

        self.rabbitmq_url = rabbitmq_url
        self._pika = pika

    def publish(self, queue_name: str, payload: dict[str, Any]) -> None:
        params = self._pika.URLParameters(self.rabbitmq_url)
        connection = self._pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=json.dumps(payload),
                properties=self._pika.BasicProperties(delivery_mode=2),
            )
        finally:
            connection.close()


def get_queue_publisher() -> QueuePublisher:
    backend = settings.QUEUE_BACKEND.lower().strip()

    if backend == "redis":
        return RedisQueuePublisher(settings.REDIS_URL)

    if backend in {"rabbitmq", "rabbit"}:
        return RabbitMQQueuePublisher(settings.RABBITMQ_URL)

    return InMemoryQueuePublisher()
