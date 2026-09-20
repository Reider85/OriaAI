"""CancelPublisher — Redis pub/sub wrapper for cancel events (ADR-013, C-3).

Channel naming convention: ``session:{session_id}:cancel``.
Publishes fire-and-forget; latency logged for observability.
"""
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class PublishError(RuntimeError):
    """Raised when the cancel message could not be published after retries."""


class CancelPublisher:
    """Publishes cancel events to Redis pub/sub channel ``session:{id}:cancel``."""

    def __init__(self, redis_client: Any) -> None:
        # redis.asyncio.Redis instance — reused from the app, not created here.
        self._redis = redis_client

    async def publish(
        self,
        session_id: str,
        reason: str,
        user_id: str | None = None,
        *,
        max_retries: int = 4,
    ) -> None:
        """Publish a cancel message. Fire-and-forget with bounded retry.

        Retry backoff: 1ms, 2ms, 4ms, 8ms (exponential, capped ~16ms total).
        Raises PublishError if all attempts fail.
        """
        channel = self._channel(session_id)
        message = json.dumps(
            {
                "reason": reason,
                "user_id": user_id,
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            separators=(",", ":"),
        )

        delay_ms = 1
        last_error: Exception | None = None
        start = time.perf_counter()
        for attempt in range(max_retries + 1):
            try:
                await self._redis.publish(channel, message)
                latency_ms = (time.perf_counter() - start) * 1000
                logger.debug(
                    "Published cancel for session %s channel=%s latency=%.2fms",
                    session_id,
                    channel,
                    latency_ms,
                )
                return
            except (RedisError, OSError) as exc:
                last_error = exc
                await self._sleep_ms(delay_ms)
                delay_ms = min(delay_ms * 2, 16)

        logger.error("Failed to publish cancel for session %s: %s", session_id, last_error)
        raise PublishError(f"cancel publish failed for session {session_id}") from last_error

    @staticmethod
    def _channel(session_id: str) -> str:
        return f"session:{session_id}:cancel"

    @staticmethod
    async def _sleep_ms(ms: int) -> None:
        import asyncio

        await asyncio.sleep(ms / 1000)