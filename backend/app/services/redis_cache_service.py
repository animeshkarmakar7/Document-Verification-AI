import hashlib
import json
from typing import Any

from app.config.settings import settings


class RedisCacheService:
    def __init__(self, redis_url: str | None = None):
        import redis

        self.client = redis.Redis.from_url(redis_url or settings.REDIS_URL)

    def get_json(self, namespace: str, key: str) -> dict[str, Any] | list | None:
        raw = self.client.get(self._key(namespace, key))
        if raw is None:
            return None
        return json.loads(raw)

    def set_json(
        self,
        namespace: str,
        key: str,
        value: dict[str, Any] | list,
        ttl_seconds: int = 300,
    ) -> None:
        self.client.setex(
            self._key(namespace, key),
            ttl_seconds,
            json.dumps(value, default=str),
        )

    def get_embedding(self, text: str) -> list[float] | None:
        raw = self.client.get(self._key("query_embedding", self._hash(text)))
        if raw is None:
            return None
        return json.loads(raw)

    def set_embedding(self, text: str, embedding: list[float], ttl_seconds: int = 3600) -> None:
        self.client.setex(
            self._key("query_embedding", self._hash(text)),
            ttl_seconds,
            json.dumps(embedding),
        )

    def _key(self, namespace: str, key: str) -> str:
        return f"legaldocai:{namespace}:{key}"

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
