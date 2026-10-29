"""agent_run MCP tool: long-running agent execution with SSE progress (H-1).

Streams ``graph.astream`` events as progress chunks over the MCP SSE endpoint
(``GET /mcp/tools/agent_run/stream``); ``POST /mcp/tools/agent_run`` drains the
stream and returns the terminal chunk.

Preview scope (ADR-004 ускорение): LLM is built through ``LLMProviderFactory``
directly (LLMRouter is chat-endpoint only), and the run skips checkpointer,
PII metadata, message persistence and the RAG pipeline — the chat endpoint
remains the full-featured path. Cancellation follows ADR-013: MCP Server does
not emit cancel events (BETA-PROMPTS H-1).
"""

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentRunArgs(BaseModel):
    """Arguments for the agent_run tool (exposed as MCP args_schema)."""

    prompt: str = Field(..., description="Task prompt for the agent")
    user_id: str = Field(default="anonymous", description="End user identifier")
    tools: list[str] | None = Field(
        default=None,
        description="Subset of tool names to enable (omit for the default tool set)",
    )
    max_iterations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Cycle-detection limit for the agent graph",
    )


def _create_llm(settings: Any, model_name: str) -> Any:
    """Build the LLM for agent_run (mirrors the chat endpoint factory path)."""
    from ..agent.provider import LLMProviderFactory

    match settings.llm_provider.upper():
        case "OPENAI":
            api_key, base_url = settings.openai_api_key, None
        case "CUSTOM-OPENAI":
            api_key, base_url = settings.custom_openai_api_key, settings.custom_openai_base_url
        case "ZAI":
            api_key, base_url = settings.zai_api_key, settings.zai_base_url
        case "ANTHROPIC":
            api_key, base_url = settings.anthropic_api_key, None
        case _:
            api_key, base_url = settings.openai_api_key, None

    extra_kwargs: dict[str, Any] = {}
    if settings.llm_provider == "ZAI" and settings.orya_proxy_url:
        extra_kwargs["orya_proxy_url"] = settings.orya_proxy_url
        extra_kwargs["orya_proxy_key"] = settings.orya_proxy_key or None

    try:
        return LLMProviderFactory.create(
            provider=settings.llm_provider,
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            **extra_kwargs,
        )
    except NotImplementedError:
        from langchain_core.language_models import FakeListChatModel

        logger.warning(
            "agent_run: provider %s not implemented — using placeholder LLM",
            settings.llm_provider,
        )
        return FakeListChatModel(
            responses=["Provider not yet implemented. Using placeholder response."]
        )


def _message_text(message: BaseMessage) -> str:
    """Flatten message content (str or list-of-parts) into plain text."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def _final_from_update(update: Any, current: str | None) -> str | None:
    """Track the best final answer across graph chunk updates."""
    if not isinstance(update, dict):
        return current
    answer = update.get("final_answer")
    if isinstance(answer, str) and answer:
        return answer
    messages = update.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, AIMessage):
                text = _message_text(message)
                if text:
                    current = text
    return current


def _to_jsonable(value: Any) -> Any:
    """Convert graph chunk values (messages, state) into JSON-safe structures."""
    if isinstance(value, BaseMessage):
        return {"type": value.type, "content": _message_text(value)}
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


async def agent_run_handler(
    prompt: str,
    user_id: str = "anonymous",
    tools: list[str] | None = None,
    max_iterations: int = 10,
) -> AsyncIterator[dict[str, Any]]:
    """Run the agent graph for *prompt* and stream progress events.

    Yields ``{"type": "progress", ...}`` per graph chunk, then exactly one
    terminal event: ``{"type": "done"|"error"|"cancelled", ...}``.
    """
    from ..agent.cycle_detection import IterationMonitor
    from ..agent.graph import GraphCancelled, build_agent_graph
    from ..agent.service import _resolve_model, resolve_tools
    from ..config import settings

    session_id = uuid.uuid4().hex
    model_name = _resolve_model(settings, settings.llm_provider)
    request_settings = {"tools_enabled": tools} if tools is not None else None
    enabled_tools = resolve_tools(request_settings)

    try:
        llm = _create_llm(settings, model_name)
        graph = build_agent_graph(
            llm,
            tools=enabled_tools,
            monitor=IterationMonitor(),
            llm_invoke_timeout_s=settings.llm_invoke_timeout_seconds,
            provider=settings.llm_provider,
            model=model_name,
        )
    except Exception as exc:
        logger.exception("agent_run: failed to build graph for session %s", session_id)
        yield {"type": "error", "session_id": session_id, "error": str(exc)}
        return

    initial_state: dict[str, Any] = {
        "messages": [HumanMessage(prompt)],
        "user_id": user_id,
        "session_id": session_id,
        "provider": settings.llm_provider,
        "model_name": model_name,
        "iteration": 0,
        "max_iterations": max_iterations,
        "final_answer": None,
    }

    logger.info(
        "agent_run start: session=%s provider=%s model=%s max_iterations=%d",
        session_id,
        settings.llm_provider,
        model_name,
        max_iterations,
    )

    final_answer: str | None = None
    try:
        async for chunk in graph.astream(initial_state):
            if isinstance(chunk, dict):
                for update in chunk.values():
                    final_answer = _final_from_update(update, final_answer)
            yield {
                "type": "progress",
                "session_id": session_id,
                "chunk": _to_jsonable(chunk),
            }
    except GraphCancelled as exc:
        reason = getattr(exc, "reason", None) or str(exc)
        logger.info("agent_run cancelled for session %s: %s", session_id, reason)
        yield {
            "type": "cancelled",
            "session_id": session_id,
            "reason": str(reason),
            "final_answer": final_answer,
        }
        return
    except Exception as exc:
        logger.exception("agent_run graph failed for session %s", session_id)
        yield {"type": "error", "session_id": session_id, "error": str(exc)}
        return

    logger.info("agent_run done: session=%s", session_id)
    yield {"type": "done", "session_id": session_id, "final_answer": final_answer}
