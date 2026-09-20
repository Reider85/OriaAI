"""CancelSubscriber — listens for cancel signals and interrupts the agent (C-4).

Subscribes to ``session:{session_id}:cancel`` on Redis, resolves the token from the
registry and cancels it. Manages a background asyncio.Task per session.

After a token is cancelled, an optional ``cancel_event_handler`` receives the parsed
cancel event for dual-stream logging (C-6): forensic (full trace) + operational
(masked user_id).
"""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from .cancel import CancellationTokenRegistry

logger = logging.getLogger(__name__)


class CancelSubscriber:
    """Redis pub/sub listener that cancels the matching session token."""

    def __init__(
        self,
        redis_client: Any,
        token_registry: CancellationTokenRegistry,
        cancel_event_handler: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self._redis = redis_client
        self._registry = token_registry
        self._on_cancel_event = cancel_event_handler
        self._tasks: dict[str, asyncio.Task] = {}

    async def subscribe(self, session_id: str) -> None:
        """Start a background task listening for cancel events on the session channel."""
        if session_id in self._tasks:
            return
        channel = f"session:{session_id}:cancel"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        started_at = datetime.now(UTC)

        async def _listener() -> None:
            try:
                async for message in pubsub.listen():
                    if message is None or message.get("type") != "message":
                        continue
                    data: dict | None = None
                    reason = "unknown"
                    user_id: str | None = None
                    try:
                        data = json.loads(message["data"])
                        reason = data.get("reason", "unknown")
                        user_id = data.get("user_id")
                    except (TypeError, json.JSONDecodeError):
                        logger.warning(
                            "Malformed cancel message for session %s", session_id, exc_info=True
                        )
                    token = self._registry.get(session_id)
                    if token is not None:
                        if not token.is_cancelled:
                            logger.info(
                                "Cancel signal received for session %s, reason=%s",
                                session_id,
                                reason,
                            )
                            await self._emit_cancel_event(
                                session_id,
                                reason,
                                user_id,
                                started_at,
                                last_node_executed=None,
                                messages_count=None,
                            )
                        token.cancel(reason)
                    # A cancel signal is terminal: stop listening for this session.
                    break
            except asyncio.CancelledError:
                pass
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except Exception:  # redis connection may be gone
                    logger.debug("Error closing pubsub for session %s", session_id, exc_info=True)

        self._tasks[session_id] = asyncio.create_task(_listener())

    async def _emit_cancel_event(
        self,
        session_id: str,
        reason: str,
        user_id: str | None,
        started_at: datetime,
        *,
        last_node_executed: str | None,
        messages_count: int | None,
        partial_answer_size_bytes: int | None = None,
    ) -> None:
        if self._on_cancel_event is None:
            return
        if started_at is None:
            duration_ms = 0
        else:
            duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        try:
            await self._on_cancel_event(
                {
                    "event_type": "session_cancelled",
                    "session_id": session_id,
                    "user_id": user_id,
                    "reason": reason,
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "partial_answer_size_bytes": partial_answer_size_bytes,
                    "last_node_executed": last_node_executed,
                    "messages_count": messages_count,
                    "duration_ms": duration_ms,
                }
            )
        except Exception:
            logger.exception(
                "cancel_event_handler failed for session %s (cancel still delivered)", session_id
            )

    async def unsubscribe(self, session_id: str) -> None:
        """Cancel the background listener task and clean up the subscription."""
        task = self._tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def unsubscribe_all(self) -> None:
        for session_id in list(self._tasks):
            await self.unsubscribe(session_id)