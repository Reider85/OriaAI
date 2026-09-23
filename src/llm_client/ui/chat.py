"""agent-service HTTP client and SSE stream parsing (ADR-001, ADR-007).

UI talks to the LangGraph agent exclusively through the SSE endpoints:

* ``POST /sessions/{session_id}/chat`` — kicks off generation;
* ``GET /sessions/{session_id}/stream`` — Server-Sent Events with tokens.

SSE protocol (ADR-007): ``event: <type>`` / ``data: <payload>`` pairs separated
by blank lines. ``token`` is the default event. Later prompts extend handling
for ``done``, ``cancelled``, ``error``, ``artifact_ready`` and ``metadata``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any, NamedTuple

import httpx

AGENT_SERVICE_URL_ENV = "AGENT_SERVICE_URL"
AGENT_SERVICE_URL_DEFAULT = "http://localhost:8000"

_STREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)
_REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)

TOKEN_EVENTS = ("token", "message")
TERMINAL_EVENTS = ("cancelled", "error")


class SSEEvent(NamedTuple):
    """One parsed Server-Sent Event (ADR-007)."""

    event: str
    data: Any
    event_id: str | None = None


class ChatStreamError(RuntimeError):
    """Raised when the SSE stream cannot be opened or read."""


def agent_service_url() -> str:
    """Return ``AGENT_SERVICE_URL`` from the environment (never hardcoded)."""
    import os

    return os.getenv(AGENT_SERVICE_URL_ENV, AGENT_SERVICE_URL_DEFAULT).rstrip("/")


def send_message(session_id: str, message: str) -> httpx.Response:
    """POST ``{"message": ...}`` to start generation for a session.

    Raises ``httpx.HTTPError`` on transport-level failures; non-2xx statuses
    are returned as-is so the caller can decide how to surface them.
    """
    url = f"{agent_service_url()}/sessions/{session_id}/chat"
    return httpx.post(url, json={"message": message}, timeout=_REQUEST_TIMEOUT)


def stream_tokens(session_id: str) -> Iterator[str]:
    """Yield assistant tokens from ``GET /sessions/{session_id}/stream``.

    The stream terminates normally on a ``done`` event. Raises
    ``ChatStreamError`` if the connection fails, the endpoint errors, or the
    server sends a terminal ``cancelled``/``error`` event.
    """
    url = f"{agent_service_url()}/sessions/{session_id}/stream"
    try:
        with httpx.stream("GET", url, timeout=_STREAM_TIMEOUT) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ChatStreamError(
                    f"agent-service returned {exc.response.status_code} for {url}"
                ) from exc
            for event in iter_sse_events(response.iter_lines()):
                if event.event in TOKEN_EVENTS:
                    token = _token_payload(event.data)
                    if token:
                        yield token
                elif event.event == "done":
                    return
                elif event.event in TERMINAL_EVENTS:
                    raise ChatStreamError(
                        f"stream closed with event={event.event}, payload={event.data!r}"
                    )
    except httpx.TransportError as exc:
        raise ChatStreamError(f"stream to agent-service failed: {exc}") from exc


def iter_sse_events(lines: Iterator[str]) -> Iterator[SSEEvent]:
    """Parse a text line iterator into SSE events (RFC 8895-style, per ADR-007).

    Unknown fields and comment lines (``:``) are ignored. ``data`` payloads that
    parse as JSON are decoded to ``dict``/objects; otherwise the raw text is kept.
    """
    event = "message"
    event_id: str | None = None
    data_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            if data_lines:
                yield SSEEvent(event=event, data=_decode_data(data_lines), event_id=event_id)
                event, event_id, data_lines = "message", None, []
            continue
        if line.startswith(":"):
            continue
        field, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)
        elif field == "id":
            event_id = value
    if data_lines:
        yield SSEEvent(event=event, data=_decode_data(data_lines), event_id=event_id)


def _decode_data(data_lines: Sequence[str]) -> Any:
    raw = "\n".join(data_lines)
    if not raw:
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _token_payload(data: Any) -> str | None:
    if isinstance(data, dict):
        token = data.get("token")
        return token if isinstance(token, str) else None
    return data if isinstance(data, str) else None


__all__ = [
    "AGENT_SERVICE_URL_DEFAULT",
    "AGENT_SERVICE_URL_ENV",
    "ChatStreamError",
    "SSEEvent",
    "agent_service_url",
    "iter_sse_events",
    "send_message",
    "stream_tokens",
]
