import asyncio
import threading
import time
from typing import Any

from app.config.settings import settings


class GeminiRequestPacer:
    def __init__(self, min_interval_seconds: float):
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative.")
        self.min_interval_seconds = float(min_interval_seconds)
        self._lock = threading.Lock()
        self._next_request_at = 0.0

    def acquire(self) -> None:
        if self.min_interval_seconds == 0:
            return

        with self._lock:
            delay = self._next_request_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._next_request_at = time.monotonic() + self.min_interval_seconds


gemini_request_pacer = GeminiRequestPacer(
    settings.GEMINI_MIN_REQUEST_INTERVAL_SECONDS
)


def wait_for_gemini_request() -> None:
    gemini_request_pacer.acquire()


async def pace_gemini_http_request(request: Any) -> None:
    await asyncio.to_thread(wait_for_gemini_request)


def create_gemini_async_http_client():
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(
            "httpx is required for rate-limited Gemini evaluation requests."
        ) from exc

    return httpx.AsyncClient(
        event_hooks={"request": [pace_gemini_http_request]}
    )
