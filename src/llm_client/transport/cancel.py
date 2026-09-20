"""CancellationToken — per-session in-memory cancellation primitive (ADR-013).

Implements the CancellationToken & CancellationTokenRegistry abstractions from
MVP-PROMPTS.md Block C-1 (used here by Block B-1 Quick Win).
"""
import asyncio
import logging
from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)


class CancellationToken:
    """Per-session cancellation flag, thread-safe via asyncio.Event.

    - cancel() is idempotent — the first reason wins, callbacks fire exactly once.
    - on_cancel() runs callbacks when the token transitions to cancelled.
    - In-memory only; Redis merely carries the signal (ADR-013).
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._event = asyncio.Event()
        self._reason: str | None = None
        self._callbacks: list[Callable[[], Coroutine[None, None, None]]] = []

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str) -> None:
        """Cancel the token. Idempotent; first reason is kept."""
        if self._event.is_set():
            return
        self._reason = reason
        self._event.set()
        for callback in self._callbacks:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(callback())
            except RuntimeError:
                # No running loop: run callback synchronously if possible.
                logger.warning(
                    "CancellationToken.cancel without running loop for session %s", self._session_id
                )

    def on_cancel(self, callback: Callable[[], Coroutine[None, None, None]]) -> None:
        """Register a callback to fire once when the token is cancelled."""
        if self._event.is_set():
            try:
                asyncio.get_running_loop().create_task(callback())
            except RuntimeError:
                logger.warning("on_cancel after cancel without running loop", exc_info=True)
            return
        self._callbacks.append(callback)

    async def wait(self, *, timeout: float | None = None) -> bool:
        """Wait until cancelled. Returns True if cancelled, False on timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False


class CancellationTokenRegistry:
    """Per-session registry of CancellationToken objects."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}

    def register(self, session_id: str) -> CancellationToken:
        token = CancellationToken(session_id)
        self._tokens[session_id] = token
        return token

    def get(self, session_id: str) -> CancellationToken | None:
        return self._tokens.get(session_id)

    def cancel(self, session_id: str, reason: str) -> bool:
        """Cancel token for session. Returns True if found and newly cancelled."""
        token = self._tokens.get(session_id)
        if token is None or token.is_cancelled:
            return False
        token.cancel(reason)
        return True

    def cleanup(self, session_id: str) -> None:
        self._tokens.pop(session_id, None)

    def active_sessions(self) -> list[str]:
        return list(self._tokens.keys())