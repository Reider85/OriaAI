"""Agent-service scaffold — FastAPI app with SSE streaming endpoints (AG-0).

Provides the real backend for the UI (replaces mock_agent_service.py).
Phase 1 routes: /health, /chat (202 async), /stream (SSE smoke-test),
/sessions/{id}/cancel (delegates to ADR-013 control-plane).

In Phase 2+ the graph (AG-1) and LLM provider (AG-2) are wired in;
this module remains the FastAPI entry point.
"""

import json
import logging
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from redis import asyncio as aioredis

from ..config import Settings
from ..transport.cancel import CancellationTokenRegistry
from ..transport.endpoint import build_cancel_router, get_session_state
from ..transport.publisher import CancelPublisher
from ..transport.subscriber import CancelSubscriber

logger = logging.getLogger(__name__)


# ── SSE helper (reused in AG-3) ───────────────────────────────────────────────


def format_sse_event(event: str, data: Any) -> str:
    """Format a single SSE event per RFC 8895.

    Returns ``event: <event>\\ndata: <payload>\\n\\n``.
    ``data`` is JSON-serialised when dict/list, otherwise str(data).
    """
    if isinstance(data, (dict, list)):
        payload = json.dumps(data, separators=(",", ":"))
    else:
        payload = str(data)
    return f"event: {event}\ndata: {payload}\n\n"


# ── Request / Response models ─────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = Field(default=None)


class ChatResponse(BaseModel):
    status: str
    session_id: str


# ── In-memory session store (Phase 1 placeholder for graph state) ─────────────

_sessions: dict[str, dict[str, Any]] = {}


# ── Application factory ───────────────────────────────────────────────────────


def create_agent_app(_settings: Settings | None = None) -> FastAPI:
    """Build and wire the agent-service FastAPI application.

    Uses the same Redis instance and cancel control-plane as the main API
    (api.py) but runs as a separate process (Principle #19).
    """
    from ..config import settings as default_settings

    settings = _settings or default_settings

    redis_url = settings.redis_url
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    registry = CancellationTokenRegistry()
    publisher = CancelPublisher(redis_client)
    state = get_session_state()
    subscriber = CancelSubscriber(redis_client, registry)

    app = FastAPI(title="LLM Client — agent-service", version="0.1.0")
    app.state.redis = redis_client
    app.state.registry = registry
    app.state.subscriber = subscriber

    # ── Cancel endpoint (ADR-013) ────────────────────────────────────────────
    app.include_router(build_cancel_router(publisher, state))

    # ── Routes ───────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/sessions/{session_id}/chat",
        response_model=ChatResponse,
        status_code=202,
    )
    async def start_chat(session_id: str, body: ChatRequest) -> ChatResponse:
        _sessions[session_id] = {
            "message": body.message,
            "user_id": body.user_id,
        }
        state.activate(session_id)
        logger.info("Chat started for session %s", session_id)
        return ChatResponse(status="ok", session_id=session_id)

    @app.get("/sessions/{session_id}/stream")
    async def stream_tokens(session_id: str) -> StreamingResponse:
        return StreamingResponse(
            _stream_generator(session_id),
            media_type="text/event-stream",
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @app.on_event("startup")
    async def _startup() -> None:
        await redis_client.ping()
        logger.info("agent-service connected to Redis at %s", redis_url)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await subscriber.unsubscribe_all()
        await redis_client.aclose()

    return app


# ── SSE stream generator (Phase 1 smoke-test: emits event: done) ─────────────


async def _stream_generator(session_id: str) -> Any:
    """Yield SSE chunks for *session_id*.

    Phase 1 (no graph): immediately emits ``event: done`` as a smoke-test.
    Phase 2+ (AG-1 graph): this will read from ``graph.astream`` via a
    background task queue and emit token / metadata / cancelled / error events.
    """
    # In Phase 2+ this reads from _sessions[session_id]["queue"]
    # For now, yield a single done event so UI gets a valid SSE stream.
    yield format_sse_event("done", {})


# ── Module-level app instance ──────────────────────────────────────────────────
app = create_agent_app()
