import atexit
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)

_producer_lock = threading.Lock()
_producer_instance = None


class KafkaPublishError(Exception):
    pass


class KafkaHealthError(Exception):
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


def _build_producer():
    try:
        from kafka import KafkaProducer
        from kafka.errors import NoBrokersAvailable
    except ImportError as exc:
        raise KafkaPublishError("kafka-python package is required for Kafka publishing.") from exc

    servers = settings.KAFKA_BOOTSTRAP_SERVERS
    logger.info("Initialising production Kafka producer", extra={"_bootstrap_servers": servers})

    try:
        producer = KafkaProducer(
            bootstrap_servers=servers,
            key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            enable_idempotence=True,
            retries=10,
            retry_backoff_ms=200,
            max_in_flight_requests_per_connection=5,
            compression_type="gzip",
            linger_ms=10,
            batch_size=16384,
            request_timeout_ms=30_000,
            delivery_timeout_ms=120_000,
            connections_max_idle_ms=540_000,
        )
    except NoBrokersAvailable as exc:
        raise KafkaHealthError(
            f"Cannot connect to Kafka broker(s) at '{servers}'. "
            "Verify Kafka is running and KAFKA_BOOTSTRAP_SERVERS is configured properly."
        ) from exc
    except Exception as exc:
        raise KafkaPublishError(f"Failed to initialise Kafka producer: {exc}") from exc

    logger.info("Production Kafka producer successfully initialised", extra={"_bootstrap_servers": servers})
    return producer


def _get_producer():
    global _producer_instance
    if _producer_instance is not None:
        return _producer_instance
    with _producer_lock:
        if _producer_instance is None:
            _producer_instance = _build_producer()
    return _producer_instance


def _close_producer():
    global _producer_instance
    if _producer_instance is not None:
        try:
            _producer_instance.flush(timeout=10)
            _producer_instance.close(timeout=10)
            logger.info("Kafka producer closed gracefully")
        except Exception as exc:
            logger.warning(f"Error during Kafka producer shutdown: {exc}")
        finally:
            _producer_instance = None


atexit.register(_close_producer)


class KafkaEventPublisher:
    def __init__(self, bootstrap_servers: str | None = None):
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS

    def publish(
        self,
        topic: str,
        key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        producer = _get_producer()
        try:
            future = producer.send(topic, key=key, value=payload)
            metadata = future.get(timeout=30)
            logger.info(
                "Kafka event published successfully",
                extra={
                    "_event": "kafka_event_published",
                    "_topic": metadata.topic,
                    "_partition": metadata.partition,
                    "_offset": metadata.offset,
                    "_key": key,
                },
            )
            return {
                "topic": metadata.topic,
                "partition": metadata.partition,
                "offset": metadata.offset,
                "key": key,
            }
        except Exception as exc:
            logger.error(
                "Kafka event publication failed",
                extra={
                    "_event": "kafka_publish_failed",
                    "_topic": topic,
                    "_key": key,
                    "_error": str(exc),
                },
            )
            raise KafkaPublishError(
                f"Failed to publish event to topic '{topic}' with key '{key}': {exc}"
            ) from exc

    def publish_dlq(
        self,
        key: str,
        original_payload: dict[str, Any],
        error_message: str,
        topic: str | None = None,
    ) -> dict[str, Any]:
        dlq_topic = topic or settings.KAFKA_DLQ_TOPIC
        dlq_payload = {
            "original_payload": original_payload,
            "error_message": error_message,
            "failed_at": datetime.now(UTC).isoformat(),
        }
        logger.warning(
            "Publishing failed event to DLQ",
            extra={"_dlq_topic": dlq_topic, "_key": key, "_error": error_message},
        )
        return self.publish(topic=dlq_topic, key=key, payload=dlq_payload)

    def health_check(self) -> bool:
        try:
            _get_producer()
            return True
        except Exception as exc:
            raise KafkaHealthError(f"Kafka health check failed: {exc}") from exc
