"""Agent-service — FastAPI app with SSE streaming and LangGraph agent (AG-0..AG-3).

Provides the real backend for the UI (replaces mock_agent_service.py).
Routes: /health, /chat (202 async graph launch), /stream (SSE token stream),
/sessions/{id}/cancel (delegates to ADR-013 control-plane).

AG-1 wires the LangGraph agent graph into /chat and /stream.
AG-2 replaces the mock LLM with LLMProviderFactory.
AG-3 implements the full SSE event protocol: token / metadata / artifact_ready /
cancelled / error / done, plus an RFC 8895 heartbeat comment line.
"""

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field
from redis import asyncio as aioredis

from ..config import Settings
from ..security.pii_detector import PIIDetectionResult, PIIDetector
from ..transport.cancel import CancellationTokenRegistry
from ..transport.endpoint import build_cancel_router, get_session_state
from ..transport.publisher import CancelPublisher
from ..transport.subscriber import CancelSubscriber
from .cycle_detection import IterationMonitor
from .graph import build_agent_graph
from .provider import LLMProviderFactory

logger = logging.getLogger(__name__)

# ── SSE protocol constants (AG-3, ADR-007) ────────────────────────────────────

#: Seconds of queue idleness before a heartbeat comment line is emitted.
#: Kept well under the 60 s idle timeout typical of reverse proxies.
HEARTBEAT_INTERVAL_SECONDS = 15.0

#: Keys used for the out-of-band control chunks pushed onto the session queue.
#: Graph payload chunks are keyed by node name, so these can never collide.
CHUNK_KEY_ERROR = "_error"
CHUNK_KEY_METADATA = "_metadata"


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


def _resolve_model(settings: Settings, provider: str) -> str:
    """Return the configured model name for *provider*.

    Phase 1 only implements OpenAI, but the per-provider fields already exist in
    Settings so this stays correct as providers are added.
    """
    if provider == "anthropic":
        return settings.anthropic_model
    return settings.openai_model


def format_metadata_payload(
    message_id: str,
    detection: PIIDetectionResult,
) -> dict[str, Any]:
    """Build the ``event: metadata`` payload for a user message (ADR-014).

    Only entity *types* and character spans are exposed — never the PII text
    itself (D-5). ``PIIEntity`` is a frozen dataclass, so it is normalised to
    plain JSON-serialisable dicts here.
    """
    return {
        "message_id": message_id,
        "pii_score": detection.score,
        "pii_entities": [
            {"type": e.type, "start": e.start, "end": e.end} for e in detection.entities
        ],
    }


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

    # ── PII detection (AG-3: metadata event source, ADR-014 D-1) ──────────────
    pii_detector = PIIDetector(
        spacy_model=settings.pii_detector_spacy_model,
        enabled=settings.pii_detector_enabled,
    )

    app = FastAPI(title="LLM Client — agent-service", version="0.1.0")
    app.state.redis = redis_client
    app.state.registry = registry
    app.state.subscriber = subscriber
    app.state.pii_detector = pii_detector

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
        model_name = _resolve_model(settings, settings.llm_provider)
        initial_state: dict[str, Any] = {
            "messages": [HumanMessage(body.message)],
            "user_id": body.user_id or "anonymous",
            "session_id": session_id,
            "provider": settings.llm_provider,
            "model_name": model_name,
            "iteration": 0,
            "max_iterations": 10,
            "final_answer": None,
        }

        # Create LLM via provider factory (AG-2)
        try:
            llm = LLMProviderFactory.create(
                provider=settings.llm_provider,
                model=model_name,
                api_key=settings.openai_api_key,
            )
        except NotImplementedError:
            # Fallback for non-implemented providers (anthropic/ollama in Phase 1)
            from langchain_core.language_models import FakeListChatModel

            llm = FakeListChatModel(
                responses=["Provider not yet implemented. Using placeholder response."]
            )

        # Build iteration monitor for cycle detection
        monitor = IterationMonitor()

        # Compile and build the graph
        graph = build_agent_graph(llm, token=token, monitor=monitor)

        # Queue for streaming chunks from background task to SSE generator
        queue: asyncio.Queue[Any] = asyncio.Queue()

        # ── PII metadata (AG-3) ──────────────────────────────────────────────
        # The metadata marker is enqueued *before* the graph task is created, so
        # the generator is guaranteed to observe it first. Detection itself runs
        # concurrently in a worker thread (PIIDetector.detect is synchronous) and
        # resolves the future, so it never delays the LLM call nor blocks the loop.
        user_message = initial_state["messages"][0]
        message_id = user_message.id or uuid4().hex
        metadata_future: asyncio.Future[PIIDetectionResult] = (
            asyncio.get_running_loop().create_future()
        )
        await queue.put({CHUNK_KEY_METADATA: metadata_future})

        if settings.pii_metadata_enabled:

            async def _detect_metadata() -> None:
                try:
                    result = await asyncio.to_thread(pii_detector.detect, body.message)
                except Exception:
                    logger.exception("PII detection failed for session %s", session_id)
                    result = PIIDetectionResult(score=0.0, entities=[])
                if not metadata_future.done():
                    metadata_future.set_result(result)

            asyncio.create_task(_detect_metadata())
        else:
            # Metadata disabled — resolve immediately with a zero score (D-1 no-op).
            metadata_future.set_result(PIIDetectionResult(score=0.0, entities=[]))

        async def _run_graph() -> None:
            """Execute graph.astream in background, push chunks to queue."""
            try:
                async for chunk in graph.astream(initial_state):
                    await queue.put(chunk)
            except Exception as exc:
                logger.exception("Graph execution failed for session %s", session_id)
                await queue.put({CHUNK_KEY_ERROR: exc})
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
            "message_id": message_id,
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


# ── SSE stream generator (AG-3: full event protocol) ──────────────────────────


def _iter_stream_messages(chunk: Any) -> list[Any]:
    """Extract LangChain messages from a ``graph.astream`` chunk.

    Handles both node-keyed chunks (``{"planner": {"messages": [...]}}``) and
    flat chunks (``{"messages": [...]}``).
    """
    if not isinstance(chunk, dict):
        return []
    messages: list[Any] = []
    if "messages" in chunk:
        flat = chunk["messages"]
        if isinstance(flat, list):
            messages.extend(flat)
    for node_output in chunk.values():
        if isinstance(node_output, dict):
            node_messages = node_output.get("messages", [])
            if isinstance(node_messages, list):
                messages.extend(node_messages)
    return messages


def _artifact_payload(content: Any) -> dict[str, Any] | None:
    """Extract a file_export result from a ToolMessage content.

    ToolMessage content is a JSON-encoded string when produced by a LangChain
    tool. Returns the decoded dict when it carries an ``artifact_id``, else
    ``None`` so non-artifact tool results are ignored.
    """
    payload: Any = content
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if isinstance(payload, dict) and payload.get("artifact_id"):
        return payload
    return None


async def _stream_generator(session_id: str) -> Any:
    """Yield SSE chunks for *session_id* (AG-3 event protocol, ADR-007).

    Reads from the background graph task via an asyncio.Queue and emits, in
    order: ``metadata`` (once, for the user message), ``token`` x N,
    ``artifact_ready`` (per file_export result), then exactly one terminal
    event — ``cancelled``, ``error`` or ``done``. An RFC 8895 heartbeat comment
    line is emitted whenever the queue is idle.
    """
    session = _sessions.get(session_id)
    if session is None:
        yield format_sse_event(
            "error",
            {"message": "Session not found", "type": "SessionNotFound"},
        )
        return

    queue: asyncio.Queue[Any] = session["queue"]
    token = session["token"]
    message_id: str = session.get("message_id") or uuid4().hex
    metadata_sent = False

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS
                )
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

            # ── PII metadata chunk (AG-3, ADR-014) ───────────────────────────
            # Emitted exactly once per stream, for the user message only.
            if isinstance(chunk, dict) and CHUNK_KEY_METADATA in chunk:
                if not metadata_sent:
                    metadata_sent = True
                    detection = await chunk[CHUNK_KEY_METADATA]
                    yield format_sse_event(
                        "metadata", format_metadata_payload(message_id, detection)
                    )
                continue

            # Check for graph execution error
            if isinstance(chunk, dict) and CHUNK_KEY_ERROR in chunk:
                exc = chunk[CHUNK_KEY_ERROR]
                # No traceback in the payload — it goes to the log streams instead.
                yield format_sse_event(
                    "error",
                    {"message": str(exc), "type": type(exc).__name__},
                )
                break

            # ── Graph payload chunk ───────────────────────────────────────────
            for msg in _iter_stream_messages(chunk):
                if isinstance(msg, ToolMessage):
                    artifact = _artifact_payload(msg.content)
                    if artifact is not None:
                        yield format_sse_event("artifact_ready", artifact)
                    continue
                content = msg.content if hasattr(msg, "content") else str(msg)
                if isinstance(content, list):
                    # Content blocks (LangChain v1): concatenate plain text parts.
                    content = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                if content:
                    yield format_sse_event("token", {"token": content})

    finally:
        # Always unsubscribe to prevent Redis listener leak (C-4)
        session_sub = session.get("subscriber")
        if session_sub is not None:
            await session_sub.unsubscribe(session_id)


# ── Module-level app instance (built lazily) ──────────────────────────────────

app: FastAPI


def __getattr__(name: str) -> object:
    """Build the module-level ``app`` on first access (PEP 562).

    ``create_agent_app()`` reads the ``settings`` singleton, which validates
    fail-fast. Constructing it at import time would make ``import
    llm_client.agent.service`` (and therefore every test importing it) depend on
    a fully valid environment. The app is still built eagerly in practice:
    ``uvicorn llm_client.agent.service:app`` and ``python -m llm_client.agent``
    both resolve the attribute before the server starts.
    """
    if name == "app":
        global app
        app = create_agent_app()
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
