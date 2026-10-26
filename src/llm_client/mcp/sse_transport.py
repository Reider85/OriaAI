"""SSE transport for MCP Server (ADR-004 ускорение Phase 3).

Reuses format_sse_event helper from Phase 1 AG-3 (ADR-007).
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)


async def format_sse_event(event_type: str, data: Any) -> str:
    """Format one SSE event. Reused from Phase 1 AG-3.

    Args:
        event_type: SSE event field (e.g. "tool_result", "error", "done").
        data: dict to JSON-serialize.
    Returns:
        "event: <type>\ndata: <json>\n\n"
    """
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event_type}\ndata: {payload}\n\n"


async def stream_tool_result(streaming_handler) -> AsyncIterator[str]:
    """Wraps async generator handler into SSE event stream.
    Yields formatted SSE events."""
    try:
        # Check if handler is an async generator
        import inspect

        if inspect.isasyncgen(streaming_handler):
            # Handler is already an async generator object
            async for chunk in streaming_handler:
                event = await format_sse_event("tool_result", chunk)
                yield event
        elif inspect.isasyncgenfunction(streaming_handler):
            # Handler is a function that returns an async generator
            async for chunk in streaming_handler():
                event = await format_sse_event("tool_result", chunk)
                yield event
        else:
            # Handler is a regular async function, await it and yield the result
            result = await streaming_handler()
            event = await format_sse_event("tool_result", result)
            yield event
    except Exception as e:
        logger.exception("SSE tool streaming failed")
        error_event = await format_sse_event("error", {"message": str(e)})
        yield error_event
    # Always emit done event
    done_event = await format_sse_event("done", {})
    yield done_event
