"""CancelSubscriber — listens for cancel signals and interrupts the agent (C-4).

Subscribes to ``session:{session_id}:cancel`` on Redis, resolves the token from the
registry and cancels it. Manages a background asyncio.Task per session.
"""
import asyncio
import json
import logging
from typing import Any

from .cancel import CancellationTokenRegistry

logger = logging.getLogger(__name__)


class CancelSubscriber:
    """Redis pub/sub listener that cancels the matching session token."""

    def __init__(self, redis_client: Any, token_registry: CancellationTokenRegistry) -> None:
        self._redis = redis_client
        self._registry = token_registry
        self._tasks: dict[str, asyncio.Task] = {}

    async def subscribe(self, session_id: str) -> None:
        """Start a background task listening for cancel events on the session channel."""
        if session_id in self._tasks:
            return
        channel = f"session:{session_id}:cancel"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)

        async def _listener() -> None:
            try:
                async for message in pubsub.listen():
                    if message is None or message.get("type") != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        reason = data.get("reason", "unknown")
                    except (TypeError, json.JSONDecodeError):
                        reason = "unknown"
                    token = self._registry.get(session_id)
                    if token is not None:
                        if not token.is_cancelled:
                            logger.info(
                                "Cancel signal received for session %s, reason=%s",
                                session_id,
                                reason,
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