"""Tests for AG-3 — SSE event protocol emission (token/metadata/artifact_ready/
cancelled/error/done) from agent-service.

Exercises ``format_sse_event``, ``format_metadata_payload`` and
``_stream_generator`` directly. The generator is driven through a fake session
whose queue is pre-populated with the same chunk shapes that ``POST /chat``
produces, so no Redis, LLM or network access is required.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from llm_client.agent import service as agent_service
from llm_client.agent.service import (
    HEARTBEAT_INTERVAL_SECONDS,
    format_metadata_payload,
    format_sse_event,
)
from llm_client.security.pii_detector import PIIDetectionResult, PIIEntity
from llm_client.transport.cancel import CancellationToken
from llm_client.ui.chat import iter_sse_events

# ── Helpers ───────────────────────────────────────────────────────────────────


class _StubSubscriber:
    """Stands in for CancelSubscriber — records unsubscribe calls."""

    def __init__(self) -> None:
        self.unsubscribed: list[str] = []

    async def unsubscribe(self, session_id: str) -> None:
        self.unsubscribed.append(session_id)


def _resolved_metadata(text: str = "hi") -> Any:
    """Build an already-resolved metadata chunk (as /chat would enqueue)."""
    fut: asyncio.Future[PIIDetectionResult] = asyncio.get_event_loop().create_future()
    fut.set_result(PIIDetectionResult(score=0.0, entities=[]))
    return {agent_service.CHUNK_KEY_METADATA: fut}, text


def _register_session(
    queue: asyncio.Queue[Any],
    token: CancellationToken | None = None,
    message_id: str | None = None,
) -> tuple[str, _StubSubscriber]:
    """Populate ``_sessions`` for a synthetic run and return (session_id, sub)."""
    session_id = f"s-{uuid4().hex[:8]}"
    subscriber = _StubSubscriber()
    _agent_service_sessions()[session_id] = {
        "message": "hi",
        "user_id": "u1",
        "task": None,
        "queue": queue,
        "token": token or CancellationToken(session_id),
        "subscriber": subscriber,
        "message_id": message_id or f"msg-{uuid4().hex[:8]}",
    }
    return session_id, subscriber


def _agent_service_sessions() -> dict[str, Any]:
    return agent_service._sessions


async def _drain(session_id: str) -> list[str]:
    """Consume the whole SSE stream for *session_id* and return raw frames."""
    return [chunk async for chunk in agent_service._stream_generator(session_id)]


def _lines(frames: list[str]) -> list[str]:
    """Split SSE frames into individual lines, as ``httpx.iter_lines()`` would."""
    lines: list[str] = []
    for frame in frames:
        lines.extend(frame.splitlines())
    return lines


def _events(frames: list[str]) -> list[tuple[str, Any]]:
    """Parse raw SSE frames into (event, decoded data) pairs.

    Frames are split into individual lines first, mirroring what
    ``httpx.Response.iter_lines()`` hands to the UI parser.
    """
    lines: list[str] = []
    for frame in frames:
        lines.extend(frame.splitlines())
    return [(e.event, e.data) for e in iter_sse_events(iter(lines))]


@pytest.fixture(autouse=True)
def _clean_sessions():
    """Keep the module-level session store isolated between tests."""
    _agent_service_sessions().clear()
    yield
    _agent_service_sessions().clear()


# ── format_sse_event ──────────────────────────────────────────────────────────


def test_format_sse_event_token():
    assert format_sse_event("token", {"token": "hello"}) == (
        'event: token\ndata: {"token":"hello"}\n\n'
    )


def test_format_sse_event_metadata():
    frame = format_sse_event(
        "metadata",
        {
            "message_id": "m1",
            "pii_score": 0.9,
            "pii_entities": [{"type": "US_SSN", "start": 11, "end": 22}],
        },
    )
    assert frame.startswith("event: metadata\ndata: ")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload["pii_score"] == 0.9
    assert payload["pii_entities"] == [{"type": "US_SSN", "start": 11, "end": 22}]


def test_format_sse_event_done_empty_payload():
    assert format_sse_event("done", {}) == "event: done\ndata: {}\n\n"


def test_format_sse_event_non_dict_payload_is_stringified():
    assert format_sse_event("cancelled", "user_cancelled") == (
        "event: cancelled\ndata: user_cancelled\n\n"
    )


def test_each_event_is_a_separate_frame():
    """Anti-pattern guard: events must not be merged into one chunk."""
    first = format_sse_event("token", {"token": "a"})
    second = format_sse_event("token", {"token": "b"})
    frames = [first, second]
    assert len(_events(frames)) == 2
    assert frames[0].count("\n\n") == 1


# ── format_metadata_payload ───────────────────────────────────────────────────


def test_metadata_payload_exposes_types_and_spans_only():
    detection = PIIDetectionResult(
        score=0.42,
        entities=[PIIEntity(type="US_SSN", start=11, end=22)],
    )
    payload = format_metadata_payload("m1", detection)
    assert payload == {
        "message_id": "m1",
        "pii_score": 0.42,
        "pii_entities": [{"type": "US_SSN", "start": 11, "end": 22}],
    }
    # Only type/start/end keys — no text-bearing key is present.
    assert set(payload["pii_entities"][0]) == {"type", "start", "end"}


def test_metadata_payload_is_json_serialisable():
    detection = PIIDetectionResult(
        score=0.1, entities=[PIIEntity(type="EMAIL_ADDRESS", start=0, end=5)]
    )
    json.dumps(format_metadata_payload("m1", detection))  # must not raise


# ── PII leak protection (D-5) ─────────────────────────────────────────────────


def test_pii_text_never_appears_in_metadata_event(pii_detector):
    """The PII literal must not leak into the SSE metadata frame (D-5)."""
    secret = "bob@example.com"
    message = secret
    detection = pii_detector.detect(message)

    assert detection.score > 0.7, "fixture must actually detect the address"
    assert any(e.type == "EMAIL_ADDRESS" for e in detection.entities)

    frame = format_sse_event("metadata", format_metadata_payload("m1", detection))
    assert secret not in frame
    assert "EMAIL_ADDRESS" in frame
    # Span offsets are exposed, the substring they cover is not.
    entity = next(e for e in detection.entities if e.type == "EMAIL_ADDRESS")
    assert message[entity.start : entity.end] == secret


def test_no_detected_pii_text_leaks_into_frame(pii_detector):
    """Property check: for any input, no substring flagged as PII is emitted."""
    message = "John Smith, email bob@example.com, phone +1 555-123-4567, id EMP-123456"
    detection = pii_detector.detect(message)
    assert detection.entities, "fixture must detect at least one entity"

    frame = format_sse_event("metadata", format_metadata_payload("m1", detection))
    for entity in detection.entities:
        assert message[entity.start : entity.end] not in frame


def test_ssn_literal_is_not_emitted_even_when_undetected(pii_detector):
    """Defence in depth: an undetected secret still must not reach the payload.

    The current Presidio setup does not flag ``US_SSN``; the metadata event only
    ever carries types and spans, so no message text can leak regardless.
    """
    secret = "123-45-6789"
    detection = pii_detector.detect(f"My SSN is {secret}")
    frame = format_sse_event("metadata", format_metadata_payload("m1", detection))
    assert secret not in frame
    assert f"My SSN is {secret}" not in frame


def test_disabled_detector_yields_zero_score(disabled_pii_detector):
    detection = disabled_pii_detector.detect("My SSN is 123-45-6789")
    payload = format_metadata_payload("m1", detection)
    assert payload["pii_score"] == 0.0
    assert payload["pii_entities"] == []


# ── Stream protocol: happy path ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_emits_metadata_then_tokens_then_done():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="Hello")]}})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    assert [e for e, _ in events] == ["metadata", "token", "done"]
    assert events[0][1]["pii_score"] == 0.0
    assert events[0][1]["pii_entities"] == []
    assert events[0][1]["message_id"].startswith("msg-")
    assert events[1][1] == {"token": "Hello"}
    assert events[2][1] == {}


@pytest.mark.asyncio
async def test_stream_emits_multiple_tokens():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    for text in ("First", "Second", "Third"):
        queue.put_nowait({"planner": {"messages": [AIMessage(content=text)]}})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    assert [e for e, _ in events] == ["metadata", "token", "token", "token", "done"]
    assert [d["token"] for e, d in events if e == "token"] == [
        "First",
        "Second",
        "Third",
    ]


@pytest.mark.asyncio
async def test_metadata_is_emitted_exactly_once():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="one")]}})
    queue.put_nowait(metadata_chunk)
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    # Only the first metadata chunk is honoured; the second is treated as a
    # graph payload chunk and yields no metadata event.
    assert [e for e, _ in events].count("metadata") == 1


# ── Stream protocol: artifact_ready ───────────────────────────────────────────

_ARTIFACT = {
    "artifact_id": "a-123",
    "format": "md",
    "filename": "artifact.md",
    "s3_key": "artifacts/a-123/artifact.md",
}


@pytest.mark.asyncio
async def test_stream_emits_artifact_ready_for_tool_message():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait(
        {
            "tool_executor": {
                "messages": [
                    ToolMessage(content=json.dumps(_ARTIFACT), tool_call_id="call-1")
                ]
            }
        }
    )
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    assert [e for e, _ in events] == ["metadata", "artifact_ready", "done"]
    assert events[1][1] == _ARTIFACT


@pytest.mark.asyncio
async def test_stream_emits_tokens_and_artifact_together():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="Saving")]}})
    queue.put_nowait(
        {
            "tool_executor": {
                "messages": [
                    ToolMessage(content=json.dumps(_ARTIFACT), tool_call_id="call-1")
                ]
            }
        }
    )
    queue.put_nowait({"final_answer": {"final_answer": "Saved"}})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    # The final_answer node returns no new messages, so it contributes no token.
    assert [e for e, _ in events] == [
        "metadata",
        "token",
        "artifact_ready",
        "done",
    ]


@pytest.mark.asyncio
async def test_non_artifact_tool_message_is_ignored():
    """A ToolMessage without artifact_id must not become artifact_ready."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait(
        {
            "tool_executor": {
                "messages": [
                    ToolMessage(content='{"status": "ok"}', tool_call_id="call-1")
                ]
            }
        }
    )
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    assert [e for e, _ in events] == ["metadata", "done"]


@pytest.mark.asyncio
async def test_stream_handles_missing_artifacts():
    """Phase 1 (pre-AG-4): no ToolMessage at all is the normal case."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="plain")]}})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    assert "artifact_ready" not in [e for e, _ in events]


# ── Stream protocol: cancelled ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_emits_cancelled_not_done():
    token = CancellationToken("s-cancel")
    token.cancel("user_cancelled")

    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="partial")]}})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue, token=token)
    events = _events(await _drain(session_id))

    assert [e for e, _ in events] == ["metadata", "token", "cancelled"]
    assert events[-1][1] == {"reason": "user_cancelled"}


@pytest.mark.asyncio
async def test_cancelled_emits_before_done():
    """Anti-pattern guard: no done event may follow a terminal event."""
    token = CancellationToken("s-cancel2")
    token.cancel("timeout")

    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait(None)

    session_id, _ = _register_session(queue, token=token)
    names = [e for e, _ in _events(await _drain(session_id))]

    assert names == ["metadata", "cancelled"]
    assert "done" not in names


# ── Stream protocol: error ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_emits_error_with_message_and_type():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="partial")]}})
    queue.put_nowait({agent_service.CHUNK_KEY_ERROR: ValueError("boom")})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    events = _events(await _drain(session_id))

    assert [e for e, _ in events] == ["metadata", "token", "error"]
    assert events[-1][1] == {"message": "boom", "type": "ValueError"}


@pytest.mark.asyncio
async def test_error_payload_excludes_traceback():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({agent_service.CHUNK_KEY_ERROR: RuntimeError("secret detail")})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    frames = await _drain(session_id)

    assert not any("Traceback" in f for f in frames)
    assert not any("agent/service.py" in f for f in frames)
    assert "secret detail" in frames[-1]


@pytest.mark.asyncio
async def test_error_is_terminal():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({agent_service.CHUNK_KEY_ERROR: ValueError("boom")})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    names = [e for e, _ in _events(await _drain(session_id))]

    assert names == ["metadata", "error"]
    assert "done" not in names


# ── Heartbeat ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heartbeat_emitted_while_queue_idle(monkeypatch):
    monkeypatch.setattr(agent_service, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)

    async def _finish_later() -> None:
        await asyncio.sleep(0.05)
        queue.put_nowait(None)

    asyncio.create_task(_finish_later())

    session_id, _ = _register_session(queue)
    frames = await _drain(session_id)

    assert ": keepalive\n\n" in frames
    # Heartbeat is a comment line — the UI parser ignores it, so no event is
    # yielded for it.
    assert [e for e, _ in _events(frames)] == ["metadata", "done"]


def test_heartbeat_interval_is_under_proxy_idle_timeout():
    assert HEARTBEAT_INTERVAL_SECONDS < 60.0


# ── Session lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_called_on_normal_completion():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait(None)

    session_id, subscriber = _register_session(queue)
    await _drain(session_id)

    assert subscriber.unsubscribed == [session_id]


@pytest.mark.asyncio
async def test_unsubscribe_called_on_error():
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({agent_service.CHUNK_KEY_ERROR: ValueError("boom")})
    queue.put_nowait(None)

    session_id, subscriber = _register_session(queue)
    await _drain(session_id)

    assert subscriber.unsubscribed == [session_id]


@pytest.mark.asyncio
async def test_unknown_session_yields_error_event():
    events = _events(await _drain("does-not-exist"))
    assert events == [
        ("error", {"message": "Session not found", "type": "SessionNotFound"})
    ]


# ── End-to-end against the UI parser ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_frames_are_parseable_by_ui_parser():
    """The exact frames the emitter produces must round-trip through chat.py."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="Hello world")]}})
    queue.put_nowait(
        {
            "tool_executor": {
                "messages": [
                    ToolMessage(content=json.dumps(_ARTIFACT), tool_call_id="c1")
                ]
            }
        }
    )
    queue.put_nowait(None)

    session_id, _ = _register_session(queue, message_id="m-42")
    parsed = list(iter_sse_events(iter(_lines(await _drain(session_id)))))

    assert [e.event for e in parsed] == [
        "metadata",
        "token",
        "artifact_ready",
        "done",
    ]
    assert parsed[0].data["message_id"] == "m-42"
    assert parsed[1].data["token"] == "Hello world"
    assert parsed[2].data["artifact_id"] == "a-123"


@pytest.mark.asyncio
async def test_newline_in_token_is_sent_as_single_data_line():
    """A multi-line token must not corrupt the frame — JSON escapes newlines."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait({"planner": {"messages": [AIMessage(content="line1\nline2")]}})
    queue.put_nowait(None)

    session_id, _ = _register_session(queue)
    parsed = list(iter_sse_events(iter(_lines(await _drain(session_id)))))

    assert parsed[1].data == {"token": "line1\nline2"}


@pytest.mark.asyncio
async def test_cancelled_latency_under_200ms():
    """C-4 DoD: event: cancelled must land quickly after the token is cancelled."""
    token = CancellationToken("s-latency")
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    queue.put_nowait(None)

    session_id, _ = _register_session(queue, token=token)
    generator = agent_service._stream_generator(session_id)

    await generator.__anext__()  # metadata
    token.cancel("user_cancelled")

    started = time.perf_counter()
    frame = await generator.__anext__()
    elapsed_ms = (time.perf_counter() - started) * 1000

    await generator.aclose()
    assert "event: cancelled" in frame
    assert '"reason":"user_cancelled"' in frame
    assert elapsed_ms < 200.0, f"cancelled took {elapsed_ms:.1f} ms"
