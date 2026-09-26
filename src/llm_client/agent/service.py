"""Agent-service — FastAPI app with SSE streaming and LangGraph agent (AG-0 + AG-1).

Provides the real backend for the UI (replaces mock_agent_service.py).
Routes: /health, /chat (202 async graph launch), /stream (SSE token stream),
/sessions/{id}/cancel (delegates to ADR-013 control-plane).

AG-1 wires the LangGraph agent graph into /chat and /stream.
AG-2 will replace the mock LLM with LLMProviderFactory.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from redis import asyncio as aioredis

from ..config import Settings
from ..transport.cancel import CancellationTokenRegistry
from ..transport.endpoint import build_cancel_router, get_session_state
from ..transport.publisher import CancelPublisher
from ..transport.subscriber import CancelSubscriber
from .cycle_detection import IterationMonitor
from .graph import build_agent_graph

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
        # Register cancellation token and subscribe to Redis cancel channel
        token = registry.register(session_id)
        await subscriber.subscribe(session_id)

        # Activate session in lifecycle tracker
        state.activate(session_id)

        # Build initial graph state
        initial_state: dict[str, Any] = {
            "messages": [HumanMessage(body.message)],
            "user_id": body.user_id or "anonymous",
            "session_id": session_id,
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "iteration": 0,
            "max_iterations": 10,
            "final_answer": None,
        }

        # Create mock LLM — placeholder until AG-2 wires real provider
        mock_llm = FakeListChatModel(responses=["Agent is not yet connected to an LLM provider. This is a placeholder response from the AG-1 graph scaffold."])

        # Build iteration monitor for cycle detection
        monitor = IterationMonitor()

        # Compile and build the graph
        graph = build_agent_graph(mock_llm, token=token, monitor=monitor)

        # Queue for streaming chunks from background task to SSE generator
        queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _run_graph() -> None:
            """Execute graph.astream in background, push chunks to queue."""
            try:
                async for chunk in graph.astream(initial_state):
                    await queue.put(chunk)
            except Exception as exc:
                logger.exception("Graph execution failed for session %s", session_id)
                await queue.put({"_error": exc})
            finally:
                await queue.put(None)  # Sentinel: stream is done

        task = asyncio.create_task(_run_graph())

        _sessions[session_id] = {
            "message": body.message,
            "user_id": body.user_id,
            "task": task,
            "queue": queue,
            "token": token,
            "subscriber": subscriber,
        }

        logger.info("Chat started for session %s (graph launched)", session_id)
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


# ── SSE stream generator (AG-1: reads from graph.astream via queue) ───────────


async def _stream_generator(session_id: str) -> Any:
    """Yield SSE chunks for *session_id*.

    Reads from the background graph task via an asyncio.Queue.
    Emits: event: token (per AIMessage), event: cancelled, event: error, event: done.
    """
    session = _sessions.get(session_id)
    if session is None:
        yield format_sse_event("error", {"message": "Session not found", "type": "SessionNotFound"})
        return

    queue: asyncio.Queue[Any] = session["queue"]
    token = session["token"]

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=30.0)
            except TimeoutError:
                # Heartbeat to keep connection alive (RFC 8895 comment line)
                yield ": keepalive\n\n"
                continue

            if chunk is None:
                # Stream finished — determine terminal event
                if token.is_cancelled:
                    yield format_sse_event("cancelled", {"reason": token.reason})
                else:
                    yield format_sse_event("done", {})
                break

            # Check for graph execution error
            if "_error" in chunk:
                exc = chunk["_error"]
                yield format_sse_event("error", {
                    "message": str(exc),
                    "type": type(exc).__name__,
                })
                break

            # Extract AIMessage from graph node output
            for node_output in chunk.values():
                messages = node_output.get("messages", []) if isinstance(node_output, dict) else []
                for msg in messages:
                    content = msg.content if hasattr(msg, "content") else str(msg)
                    if content:
                        yield format_sse_event("token", {"token": content})

    finally:
        # Always unsubscribe to prevent Redis listener leak (C-4)
        session_sub = session.get("subscriber")
        if session_sub is not None:
            await session_sub.unsubscribe(session_id)


# ── Module-level app instance ──────────────────────────────────────────────────
app = create_agent_app()
