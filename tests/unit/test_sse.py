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
    _build_tool_result_preview,
    _parse_tool_full_results,
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
    message: str = "hi",
) -> tuple[str, _StubSubscriber]:
    """Populate ``_sessions`` for a synthetic run and return (session_id, sub)."""
    session_id = f"s-{uuid4().hex[:8]}"
    subscriber = _StubSubscriber()
    _agent_service_sessions()[session_id] = {
        "message": message,
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

    # H-4: file_export closes both lifecycles — artifact_ready (Phase 1 download
    # buttons) and tool_result (Phase 2 tool-call preview).
    assert [e for e, _ in events] == [
        "metadata",
        "artifact_ready",
        "tool_result",
        "done",
    ]
    assert events[1][1] == _ARTIFACT
    assert events[2][1] == {
        "tool_call_id": "call-1",
        "tool_name": "unknown",
        "preview": {
            "artifact_id": "a-123",
            "format": "md",
            "filename": "artifact.md",
        },
        "full_results": None,
    }


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
        "tool_result",
        "done",
    ]


@pytest.mark.asyncio
async def test_non_artifact_tool_message_emits_tool_result_only():
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

    # An unrecognised payload still closes the tool lifecycle, with an empty
    # preview — never an artifact_ready.
    assert [e for e, _ in events] == ["metadata", "tool_result", "done"]
    assert events[1][1]["preview"] == {}
    assert events[1][1]["full_results"] is None


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
        "tool_result",
        "done",
    ]
    assert parsed[0].data["message_id"] == "m-42"
    assert parsed[1].data["token"] == "Hello world"
    assert parsed[2].data["artifact_id"] == "a-123"
    assert parsed[3].data["preview"]["artifact_id"] == "a-123"


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


# ── H-4: tool_call / tool_result / retrieved_docs ────────────────────────────

_RAG_CHUNKS = [
    {
        "source_uri": "s3://doc1.pdf",
        "title": "T1",
        "page": 1,
        "content_preview": "p1",
        "score": 0.93,
    },
    {
        "source_uri": "s3://doc2.pdf",
        "title": "T2",
        "page": None,
        "content_preview": "p2",
        "score": 0.71,
    },
]
_RAG_RESULT = {
    "chunks": _RAG_CHUNKS,
    "chunk_count": 2,
    "top_score": 0.93,
    "source_uris": ["s3://doc1.pdf", "s3://doc2.pdf"],
}
_WEB_RESULTS = [
    {"title": "T1", "url": "http://a", "snippet": "s1", "score": 0.9},
    {"title": "T2", "url": "http://b", "snippet": "s2", "score": 0.7},
]


def _ai_tool_call(name: str, args: dict[str, Any], call_id: str = "tc-1") -> AIMessage:
    """AIMessage carrying a single tool_call, as the planner would return it."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def _planner_chunk(msg: Any) -> dict[str, Any]:
    return {"planner": {"messages": [msg]}}


def _executor_chunk(msg: ToolMessage) -> dict[str, Any]:
    return {"tool_executor": {"messages": [msg]}}


def _queue_with(*chunks: Any) -> asyncio.Queue[Any]:
    """Queue pre-loaded with the metadata chunk, *chunks*, and the done sentinel."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)
    for item in chunks:
        queue.put_nowait(item)
    queue.put_nowait(None)
    return queue


def _names(frames: list[str]) -> list[str]:
    return [e for e, _ in _events(frames)]


def _payloads(frames: list[str], event: str) -> list[Any]:
    return [d for e, d in _events(frames) if e == event]


# ── Payload helpers ──────────────────────────────────────────────────────────


def test_build_tool_result_preview_web_search():
    assert _build_tool_result_preview(json.dumps(_WEB_RESULTS)) == {"snippet_count": 2}


def test_build_tool_result_preview_rag_query():
    assert _build_tool_result_preview(json.dumps(_RAG_RESULT)) == {
        "chunk_count": 2,
        "top_score": 0.93,
    }


def test_build_tool_result_preview_file_export():
    assert _build_tool_result_preview(json.dumps(_ARTIFACT)) == {
        "artifact_id": "a-123",
        "format": "md",
        "filename": "artifact.md",
    }


def test_build_tool_result_preview_failed_tool():
    assert _build_tool_result_preview('{"error": "Error: boom"}') == {"error": "Error: boom"}


def test_build_tool_result_preview_unrecognised_payload_is_empty():
    assert _build_tool_result_preview('{"status": "ok"}') == {}
    assert _build_tool_result_preview("not json at all") == {}


def test_build_tool_result_preview_rag_query_chunk_count_falls_back_to_len():
    preview = _build_tool_result_preview(json.dumps({"chunks": _RAG_CHUNKS}))
    assert preview == {"chunk_count": 2, "top_score": 0.0}


def test_parse_tool_full_results_returns_list_payloads():
    assert _parse_tool_full_results(json.dumps(_WEB_RESULTS)) == _WEB_RESULTS


def test_parse_tool_full_results_ignores_rag_and_artifact_payloads():
    assert _parse_tool_full_results(json.dumps(_RAG_RESULT)) is None
    assert _parse_tool_full_results(json.dumps(_ARTIFACT)) is None
    assert _parse_tool_full_results("plain text") is None


# ── tool_call ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_emits_tool_call_with_id_name_and_args():
    queue = _queue_with(_planner_chunk(_ai_tool_call("web_search", {"query": "x"})))
    session_id, _ = _register_session(queue)

    events = _events(await _drain(session_id))

    assert events[1] == (
        "tool_call",
        {"tool_call_id": "tc-1", "tool_name": "web_search", "args": {"query": "x"}},
    )


@pytest.mark.asyncio
async def test_stream_emits_no_tool_call_event_without_tool_calls():
    queue = _queue_with(_planner_chunk(AIMessage(content="plain answer")))
    session_id, _ = _register_session(queue)

    assert _names(await _drain(session_id)) == ["metadata", "token", "done"]


@pytest.mark.asyncio
async def test_tool_name_resolved_from_tracked_call_when_message_omits_it():
    """ToolMessage without .name still resolves via the recorded tool_call."""
    queue = _queue_with(
        _planner_chunk(_ai_tool_call("web_search", {"query": "x"}, call_id="tc-9")),
        _executor_chunk(ToolMessage(content=json.dumps(_WEB_RESULTS), tool_call_id="tc-9")),
    )
    session_id, _ = _register_session(queue)

    result = _payloads(await _drain(session_id), "tool_result")

    assert result[0]["tool_name"] == "web_search"


# ── tool_result ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_emits_tool_result_for_web_search():
    queue = _queue_with(
        _planner_chunk(_ai_tool_call("web_search", {"query": "x"})),
        _executor_chunk(
            ToolMessage(
                content=json.dumps(_WEB_RESULTS),
                tool_call_id="tc-1",
                name="web_search",
            )
        ),
    )
    session_id, _ = _register_session(queue)
    frames = await _drain(session_id)
    events = _events(frames)

    assert _names(frames) == ["metadata", "tool_call", "tool_result", "done"]
    assert events[2][1] == {
        "tool_call_id": "tc-1",
        "tool_name": "web_search",
        "preview": {"snippet_count": 2},
        "full_results": _WEB_RESULTS,
    }


@pytest.mark.asyncio
async def test_stream_emits_retrieved_docs_for_rag_query_tool_call():
    """Chunks travel in retrieved_docs, never inside tool_result (anti-pattern)."""
    queue = _queue_with(
        _planner_chunk(_ai_tool_call("rag_query", {"query": "q"}, call_id="tc-rag")),
        _executor_chunk(
            ToolMessage(
                content=json.dumps(_RAG_RESULT),
                tool_call_id="tc-rag",
                name="rag_query",
            )
        ),
    )
    session_id, _ = _register_session(queue)
    frames = await _drain(session_id)
    events = _events(frames)

    assert _names(frames) == [
        "metadata",
        "tool_call",
        "tool_result",
        "retrieved_docs",
        "done",
    ]
    result, docs = events[2][1], events[3][1]
    assert result["preview"] == {"chunk_count": 2, "top_score": 0.93}
    assert result["full_results"] is None
    assert "chunks" not in result
    assert docs == {
        "tool_call_id": "tc-rag",
        "chunk_count": 2,
        "top_score": 0.93,
        "source_uris": ["s3://doc1.pdf", "s3://doc2.pdf"],
        "chunks": _RAG_CHUNKS,
    }


@pytest.mark.asyncio
async def test_stream_emits_tool_result_for_failed_tool():
    queue = _queue_with(
        _planner_chunk(_ai_tool_call("web_search", {"query": "x"})),
        _executor_chunk(
            ToolMessage(
                content=json.dumps({"error": "Error: TAVILY_API_KEY not set"}),
                tool_call_id="tc-1",
                name="web_search",
            )
        ),
    )
    session_id, _ = _register_session(queue)

    result = _payloads(await _drain(session_id), "tool_result")

    assert result[0]["preview"] == {"error": "Error: TAVILY_API_KEY not set"}


@pytest.mark.asyncio
async def test_stream_emits_no_retrieved_docs_for_unrelated_tool():
    queue = _queue_with(
        _executor_chunk(
            ToolMessage(
                content=json.dumps({"items": ["a", "b"]}),
                tool_call_id="tc-1",
                name="some_tool",
            )
        ),
    )
    session_id, _ = _register_session(queue)

    assert "retrieved_docs" not in _names(await _drain(session_id))


# ── retrieved_docs from the rag_retriever node ───────────────────────────────


@pytest.mark.asyncio
async def test_stream_emits_synthetic_tool_call_before_node_retrieved_docs():
    queue = _queue_with({"rag_retriever": {"retrieved_docs": _RAG_CHUNKS}})
    session_id, _ = _register_session(queue, message="найди документ")
    frames = await _drain(session_id)
    events = _events(frames)

    assert _names(frames) == [
        "metadata",
        "tool_call",
        "retrieved_docs",
        "done",
    ]
    assert events[1][1] == {
        "tool_call_id": agent_service.RAG_RETRIEVER_TOOL_CALL_ID,
        "tool_name": "rag_query",
        "args": {"query": "найди документ"},
    }
    assert events[2][1]["tool_call_id"] == agent_service.RAG_RETRIEVER_TOOL_CALL_ID
    assert events[2][1]["chunk_count"] == 2


@pytest.mark.asyncio
async def test_flat_retrieved_docs_chunk_is_supported():
    queue = _queue_with({"retrieved_docs": _RAG_CHUNKS[:1]})
    session_id, _ = _register_session(queue)

    docs = _payloads(await _drain(session_id), "retrieved_docs")

    assert docs[0]["chunk_count"] == 1
    assert docs[0]["top_score"] == 0.93


@pytest.mark.asyncio
async def test_empty_retrieved_docs_emits_no_event():
    queue = _queue_with({"rag_retriever": {"retrieved_docs": []}})
    session_id, _ = _register_session(queue)

    assert _names(await _drain(session_id)) == ["metadata", "done"]


@pytest.mark.asyncio
async def test_node_retrieval_suppressed_after_rag_query_tool_call():
    """Same question twice must not render the citations panel twice."""
    queue = _queue_with(
        _planner_chunk(_ai_tool_call("rag_query", {"query": "найди документ"}, call_id="tc-rag")),
        _executor_chunk(
            ToolMessage(
                content=json.dumps(_RAG_RESULT),
                tool_call_id="tc-rag",
                name="rag_query",
            )
        ),
        {"rag_retriever": {"retrieved_docs": _RAG_CHUNKS}},
    )
    session_id, _ = _register_session(queue, message="найди документ")
    names = _names(await _drain(session_id))

    assert names == ["metadata", "tool_call", "tool_result", "retrieved_docs", "done"]
    assert names.count("tool_call") == 1, "no synthetic tool_call for a duplicated query"


@pytest.mark.asyncio
async def test_node_retrieval_reuses_pending_rag_query_call_id():
    """A rag_query call whose result carried no chunks still owns the preview."""
    queue = _queue_with(
        _planner_chunk(_ai_tool_call("rag_query", {"query": "найди документ"}, call_id="tc-rag")),
        _executor_chunk(
            ToolMessage(
                content=json.dumps({"error": "Error: no corpus"}),
                tool_call_id="tc-rag",
                name="rag_query",
            )
        ),
        {"rag_retriever": {"retrieved_docs": _RAG_CHUNKS}},
    )
    session_id, _ = _register_session(queue, message="найди документ")
    frames = await _drain(session_id)
    names = _names(frames)

    assert names.count("tool_call") == 1
    assert names[-2:] == ["retrieved_docs", "done"]
    assert _payloads(frames, "retrieved_docs")[0]["tool_call_id"] == "tc-rag"


@pytest.mark.asyncio
async def test_node_retrieval_emitted_when_query_differs():
    """Multi-hop: a decomposed query is genuinely new context — both panels."""
    queue = _queue_with(
        _planner_chunk(_ai_tool_call("rag_query", {"query": "пункт 5 договора"}, call_id="tc-a")),
        _executor_chunk(
            ToolMessage(
                content=json.dumps(_RAG_RESULT),
                tool_call_id="tc-a",
                name="rag_query",
            )
        ),
        {"rag_retriever": {"retrieved_docs": _RAG_CHUNKS}},
    )
    session_id, _ = _register_session(queue, message="найди документ")
    docs = _payloads(await _drain(session_id), "retrieved_docs")

    assert len(docs) == 2
    assert docs[0]["tool_call_id"] == "tc-a"
    assert docs[1]["tool_call_id"] == agent_service.RAG_RETRIEVER_TOOL_CALL_ID


# ── Ordering ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_and_tool_events_are_interleaved_in_order():
    queue = _queue_with(
        _planner_chunk(AIMessage(content="Looking it up")),
        _planner_chunk(_ai_tool_call("web_search", {"query": "x"})),
        _executor_chunk(
            ToolMessage(content=json.dumps(_WEB_RESULTS), tool_call_id="tc-1", name="web_search")
        ),
        _planner_chunk(AIMessage(content="Here is what I found")),
    )
    session_id, _ = _register_session(queue)

    assert _names(await _drain(session_id)) == [
        "metadata",
        "token",
        "tool_call",
        "tool_result",
        "token",
        "done",
    ]


@pytest.mark.asyncio
async def test_single_ai_message_emits_tokens_then_tool_calls():
    msg = AIMessage(
        content="Working on it",
        tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "tc-1"}],
    )
    queue = _queue_with(_planner_chunk(msg))
    session_id, _ = _register_session(queue)

    assert _names(await _drain(session_id)) == ["metadata", "token", "tool_call", "done"]


# ── UI parser ────────────────────────────────────────────────────────────────


def test_iter_sse_events_parses_tool_call():
    events = list(
        iter_sse_events(
            iter(
                [
                    "event: tool_call",
                    'data: {"tool_call_id": "tc1", "tool_name": "web_search", "args": {"q": "x"}}',
                    "",
                ]
            )
        )
    )

    assert events[0].event == "tool_call"
    assert events[0].data == {
        "tool_call_id": "tc1",
        "tool_name": "web_search",
        "args": {"q": "x"},
    }


def test_iter_sse_events_parses_retrieved_docs():
    events = list(
        iter_sse_events(
            iter(
                [
                    "event: retrieved_docs",
                    'data: {"tool_call_id": "tc1", "chunk_count": 2, "top_score": 0.93}',
                    "",
                ]
            )
        )
    )

    assert events[0].event == "retrieved_docs"
    assert events[0].data["chunk_count"] == 2


def test_iter_sse_events_ignores_heartbeat_between_tool_events():
    events = list(
        iter_sse_events(
            iter(
                [
                    ": keepalive",
                    "",
                    "event: tool_result",
                    'data: {"tool_call_id": "tc1", "preview": {}}',
                    "",
                    ": keepalive",
                    "",
                ]
            )
        )
    )

    assert [e.event for e in events] == ["tool_result"]


# ── Full flow (CI: sse-tool-events-staging) ──────────────────────────────────


class _StubTool:
    """BaseTool stand-in with a fixed result — no network, no LLM."""

    def __init__(self, name: str, result: Any) -> None:
        self.name = name
        self._result = result
        self.calls: list[dict] = []

    async def ainvoke(self, args: dict) -> Any:
        self.calls.append(args)
        return self._result


class _RagToolCallLLM:
    """Fake LLM: first a rag_query tool_call, then plain text."""

    def __init__(self, query: str) -> None:
        self._query = query
        self._calls = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _RagToolCallLLM:
        return self

    async def ainvoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        self._calls += 1
        if self._calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "rag_query",
                        "args": {"query": self._query},
                        "id": "call_rag_1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Готово, вот ответ по документации.")


class _RecordingPipeline:
    """rag_pipeline stand-in — records every retrieval the graph performs."""

    def __init__(self) -> None:
        self.retrieve_calls: list[dict] = []

    async def retrieve(self, query: str, top_k: int = 5) -> dict:
        self.retrieve_calls.append({"query": query, "top_k": top_k})
        return _RAG_RESULT


class _RecordingClient:
    """UIClient stand-in capturing the tool-call previews G-1 renders."""

    def __init__(self) -> None:
        self.previews: list[dict] = []

    def render_tool_call(
        self,
        tool_name: str,
        args: dict,
        status: str = "running",
        result_preview: dict | None = None,
    ) -> None:
        self.previews.append(
            {
                "tool_name": tool_name,
                "args": args,
                "status": status,
                "result_preview": result_preview,
            }
        )


@pytest.mark.asyncio
async def test_sse_tool_events_staging(monkeypatch):
    """End-to-end: graph → SSE frames → UI parser → G-1 preview + G-2 citations.

    Exercises the full Phase 2 flow for an RAG-intent message: the planner calls
    ``rag_query`` as a tool, the citations panel must be rendered exactly once,
    and the ``rag_retriever`` heuristic route must not repeat the same retrieval.
    """
    from langchain_core.messages import HumanMessage

    from llm_client.agent.graph import build_agent_graph
    from llm_client.ui import render

    user_message = "найди документ про онбординг"
    pipeline = _RecordingPipeline()
    rag_tool = _StubTool("rag_query", _RAG_RESULT)
    graph = build_agent_graph(
        _RagToolCallLLM(query=user_message),  # type: ignore[arg-type]
        tools=[rag_tool],
        rag_pipeline=pipeline,
    )

    state: dict[str, Any] = {
        "messages": [HumanMessage(user_message)],
        "user_id": "u1",
        "session_id": "s-staging",
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": 0,
        "max_iterations": 10,
        "final_answer": None,
    }

    queue: asyncio.Queue[Any] = asyncio.Queue()
    metadata_chunk, _ = _resolved_metadata()
    queue.put_nowait(metadata_chunk)

    async def _feed_graph() -> None:
        async for graph_chunk in graph.astream(state):
            queue.put_nowait(graph_chunk)
        queue.put_nowait(None)

    feed = asyncio.create_task(_feed_graph())
    session_id, _ = _register_session(queue, message=user_message)
    frames = await _drain(session_id)
    await feed

    names = _names(frames)
    assert names == [
        "metadata",
        "tool_call",
        "tool_result",
        "retrieved_docs",
        "token",
        "done",
    ]

    # The graph must not have run the heuristic retrieval a second time.
    assert pipeline.retrieve_calls == []
    assert rag_tool.calls == [{"query": user_message}]

    # G-1 preview + G-2 citations, fed through the same handler the UI uses.
    citations: list[list[dict]] = []
    monkeypatch.setattr(
        render, "_render_rag_citations_fragment", lambda chunks: citations.append(list(chunks))
    )
    client = _RecordingClient()
    pending: dict[str, dict] = {}
    for event in iter_sse_events(iter(_lines(frames))):
        if event.event in ("tool_call", "tool_result", "retrieved_docs"):
            render.handle_tool_event(event.event, event.data, client, pending)

    assert len(citations) == 1, "citations panel rendered more than once"
    assert citations[0] == _RAG_CHUNKS
    assert list(pending) == ["call_rag_1"]
    assert pending["call_rag_1"]["status"] == "done"
    assert pending["call_rag_1"]["result_preview"]["chunk_count"] == 2
    assert pending["call_rag_1"]["result_preview"]["source_uris"] == _RAG_RESULT["source_uris"]
    # G-1 preview renders on tool_call, then once per result event; retrieved_docs
    # upgrades the preview to the citation-bearing variant.
    assert [p["status"] for p in client.previews] == ["running", "done", "done"]
    assert client.previews[-1]["result_preview"] == {
        "chunk_count": 2,
        "top_score": 0.93,
        "source_uris": _RAG_RESULT["source_uris"],
    }
