"""Per-session graph runtime context for forensic cancel records (C-6).

Tracks the last executed node, message count, and partial-answer size while
the agent graph streams. Context is kept in-process and mirrored to Redis so
``CancelSubscriber`` (possibly in another process) can populate forensic
fields that would otherwise be hardcoded as ``None``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Redis key prefix for session runtime snapshots (pub/sub DB 0, key space).
RUNTIME_CONTEXT_KEY_PREFIX = "session:runtime:"

#: TTL for runtime snapshots — long enough to outlive in-flight cancels.
RUNTIME_CONTEXT_TTL_SECONDS = 3600


@dataclass
class SessionRuntimeContext:
    """Snapshot of agent-graph runtime state at cancel time (C-6 forensic fields)."""

    last_node_executed: str | None = None
    messages_count: int | None = None
    partial_answer_size_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SessionRuntimeContext:
        if not data:
            return cls()
        return cls(
            last_node_executed=_opt_str(data.get("last_node_executed")),
            messages_count=_opt_int(data.get("messages_count")),
            partial_answer_size_bytes=_opt_int(data.get("partial_answer_size_bytes")),
        )


def runtime_context_key(session_id: str) -> str:
    return f"{RUNTIME_CONTEXT_KEY_PREFIX}{session_id}"


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _opt_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


class SessionRuntimeRegistry:
    """In-process store of live ``SessionRuntimeContext`` objects."""

    def __init__(self) -> None:
        self._contexts: dict[str, SessionRuntimeContext] = {}

    def get(self, session_id: str) -> SessionRuntimeContext | None:
        return self._contexts.get(session_id)

    def set(self, session_id: str, context: SessionRuntimeContext) -> None:
        self._contexts[session_id] = context

    def update(
        self,
        session_id: str,
        *,
        last_node_executed: str | None = None,
        messages_count: int | None = None,
        partial_answer_size_bytes: int | None = None,
    ) -> SessionRuntimeContext:
        ctx = self._contexts.get(session_id)
        if ctx is None:
            ctx = SessionRuntimeContext()
            self._contexts[session_id] = ctx
        if last_node_executed is not None:
            ctx.last_node_executed = last_node_executed
        if messages_count is not None:
            ctx.messages_count = messages_count
        if partial_answer_size_bytes is not None:
            ctx.partial_answer_size_bytes = partial_answer_size_bytes
        return ctx

    def clear(self, session_id: str) -> None:
        self._contexts.pop(session_id, None)


_default_registry = SessionRuntimeRegistry()


def get_runtime_registry() -> SessionRuntimeRegistry:
    return _default_registry


async def save_runtime_context(
    redis_client: Any,
    session_id: str,
    context: SessionRuntimeContext | dict[str, Any] | None,
) -> None:
    """Best-effort Redis mirror of runtime context for cross-process consumers."""
    if redis_client is None or context is None:
        return
    payload = context.to_dict() if isinstance(context, SessionRuntimeContext) else context
    try:
        await redis_client.set(
            runtime_context_key(session_id),
            json.dumps(payload, separators=(",", ":")),
            ex=RUNTIME_CONTEXT_TTL_SECONDS,
        )
    except Exception:
        logger.debug("Failed to persist runtime context for session %s", session_id, exc_info=True)


async def load_runtime_context(
    redis_client: Any,
    session_id: str,
) -> dict[str, Any] | None:
    """Load runtime context from Redis. Returns None when missing/unreadable."""
    if redis_client is None:
        return None
    try:
        raw = await redis_client.get(runtime_context_key(session_id))
    except Exception:
        logger.debug("Failed to load runtime context for session %s", session_id, exc_info=True)
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


async def delete_runtime_context(redis_client: Any, session_id: str) -> None:
    if redis_client is None:
        return
    try:
        await redis_client.delete(runtime_context_key(session_id))
    except Exception:
        logger.debug("Failed to delete runtime context for session %s", session_id, exc_info=True)


def extract_forensic_fields(context: dict[str, Any] | SessionRuntimeContext | None) -> dict[str, Any]:
    """Normalise runtime context into the three C-6 forensic field values."""
    if context is None:
        data: dict[str, Any] = {}
    elif isinstance(context, SessionRuntimeContext):
        data = context.to_dict()
    elif isinstance(context, dict):
        data = context
    else:
        data = {}
    return {
        "last_node_executed": _opt_str(data.get("last_node_executed")),
        "messages_count": _opt_int(data.get("messages_count")),
        "partial_answer_size_bytes": _opt_int(data.get("partial_answer_size_bytes")),
    }
