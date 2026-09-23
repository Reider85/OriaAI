"""Unit tests for llm_client.ui.chat (UI-0 SSE streaming, ADR-007)."""

from collections.abc import Iterator

import httpx
import pytest

from llm_client.ui import chat

SSE_SAMPLE = """\
data: Hello
data: world

event: token
data: {"token": "!"}

id: 42
event: done
data: {}

"""


def test_iter_sse_events_parses_multiple_events():
    events = list(chat.iter_sse_events(iter(SSE_SAMPLE.splitlines())))
    assert [e.event for e in events] == ["message", "token", "done"]
    assert events[0].data == "Hello\nworld"
    assert events[1].data == {"token": "!"}
    assert events[2].event_id == "42"


def test_iter_sse_events_default_event_is_message():
    events = list(chat.iter_sse_events(iter(["data: raw", "", "data: more"])))
    assert events == [
        chat.SSEEvent(event="message", data="raw", event_id=None),
        chat.SSEEvent(event="message", data="more", event_id=None),
    ]


def test_iter_sse_events_skips_comments_and_unknown_fields():
    lines = [": comment", "retry: 5000", "", "data: hello", ""]
    events = list(chat.iter_sse_events(iter(lines)))
    assert events == [chat.SSEEvent(event="message", data="hello", event_id=None)]


def test_iter_sse_events_decodes_json_payloads():
    events = list(chat.iter_sse_events(iter(['data: {"a": 1}', ""])))
    assert events[0].data == {"a": 1}


def test_iter_sse_events_invalid_json_keeps_text():
    events = list(chat.iter_sse_events(iter(["data: not-json", ""])))
    assert events[0].data == "not-json"


def test_sse_sample_round_trip_with_generator():
    assert isinstance(chat.iter_sse_events(iter([])), Iterator)


class FakeStreamResponse:
    def __init__(self, lines: list[str] | None = None, error: Exception | None = None):
        self._lines = lines or []
        self._error = error

    def __enter__(self):
        if self._error:
            raise self._error
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def raise_for_status(self) -> None:
        pass

    def iter_lines(self):
        return iter(self._lines)


def test_stream_tokens_yields_tokens_until_done(monkeypatch):
    lines = ["data: Hello", "", 'data: {"token": " world"}', "", "event: done", "data: {}", ""]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    assert list(chat.stream_tokens("sid-1")) == ["Hello", " world"]


def test_stream_tokens_captures_artifact_ready(monkeypatch):
    lines = [
        "data: Hello",
        "",
        "event: artifact_ready",
        'data: {"artifact_id": "a1", "format": "md", "filename": "notes.md", "s3_key": "k"}',
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_artifacts()
    assert list(chat.stream_tokens("sid-1")) == ["Hello"]
    artifacts = chat.get_pending_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_id"] == "a1"
    assert artifacts[0]["format"] == "md"


def test_get_pending_artifacts_returns_copy(monkeypatch):
    lines = [
        "event: artifact_ready",
        'data: {"artifact_id": "a1", "format": "txt", "filename": "f.txt", "s3_key": "k"}',
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_artifacts()
    list(chat.stream_tokens("sid-1"))
    artifacts = chat.get_pending_artifacts()
    artifacts[0]["artifact_id"] = "mutated"
    assert chat.get_pending_artifacts()[0]["artifact_id"] == "a1"


def test_clear_pending_artifacts_resets_buffer(monkeypatch):
    lines = [
        "event: artifact_ready",
        'data: {"artifact_id": "a1", "format": "txt", "filename": "f.txt", "s3_key": "k"}',
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_artifacts()
    list(chat.stream_tokens("sid-1"))
    assert len(chat.get_pending_artifacts()) == 1
    chat.clear_pending_artifacts()
    assert chat.get_pending_artifacts() == []


def test_stream_tokens_ignores_invalid_artifact_payload(monkeypatch):
    lines = [
        "event: artifact_ready",
        "data: not-json",
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_artifacts()
    assert list(chat.stream_tokens("sid-1")) == []
    assert chat.get_pending_artifacts() == []


def test_stream_tokens_raises_on_transport_error(monkeypatch):
    monkeypatch.setattr(
        chat.httpx,
        "stream",
        lambda *a, **k: FakeStreamResponse(error=httpx.TransportError("boom")),
    )
    with pytest.raises(chat.ChatStreamError, match="boom"):
        list(chat.stream_tokens("sid-1"))


def test_stream_tokens_raises_on_cancelled_event(monkeypatch):
    lines = ["data: partial", "", "event: cancelled", 'data: {"reason": "user_cancelled"}', ""]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    with pytest.raises(chat.ChatStreamError, match="cancelled"):
        list(chat.stream_tokens("sid-1"))


def test_stream_tokens_cancelled_carries_status_and_reason(monkeypatch):
    lines = ["data: partial", "", "event: cancelled", 'data: {"reason": "user_cancelled"}', ""]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    with pytest.raises(chat.ChatStreamError) as excinfo:
        list(chat.stream_tokens("sid-1"))
    assert excinfo.value.status == "cancelled"
    assert excinfo.value.detail == "user_cancelled"


def test_stream_tokens_error_carries_status_and_message(monkeypatch):
    lines = ["event: error", 'data: {"message": "LLM provider failed"}', ""]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    with pytest.raises(chat.ChatStreamError) as excinfo:
        list(chat.stream_tokens("sid-1"))
    assert excinfo.value.status == "error"
    assert excinfo.value.detail == "LLM provider failed"


def test_stream_tokens_cancelled_without_reason_detail_is_none(monkeypatch):
    lines = ["event: cancelled", "data: {}", ""]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    with pytest.raises(chat.ChatStreamError) as excinfo:
        list(chat.stream_tokens("sid-1"))
    assert excinfo.value.status == "cancelled"
    assert excinfo.value.detail is None


def test_stream_tokens_ignores_unrecognised_events(monkeypatch):
    lines = [
        "data: hi",
        "",
        "event: unknown_thing",
        "data: {}",
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    assert list(chat.stream_tokens("sid-1")) == ["hi"]


def test_stream_tokens_ignores_metadata_event(monkeypatch):
    lines = [
        "event: metadata",
        'data: {"message_id": "m1", "pii_score": 0.1}',
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    assert list(chat.stream_tokens("sid-1")) == []


def test_stream_tokens_buffers_metadata_event(monkeypatch):
    lines = [
        "event: metadata",
        'data: {"message_id": "m1", "pii_score": 0.9, "pii_entities": ["US_SSN"]}',
        "",
        "data: Hello",
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_metadata()
    assert list(chat.stream_tokens("sid-1")) == ["Hello"]
    metadata = chat.get_pending_metadata()
    assert len(metadata) == 1
    assert metadata[0]["message_id"] == "m1"
    assert metadata[0]["pii_score"] == 0.9
    assert metadata[0]["pii_entities"] == ["US_SSN"]


def test_stream_tokens_ignores_metadata_without_message_id(monkeypatch):
    lines = [
        "event: metadata",
        'data: {"pii_score": 0.5}',
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_metadata()
    assert list(chat.stream_tokens("sid-1")) == []
    assert chat.get_pending_metadata() == []


def test_stream_tokens_metadata_calls_callback(monkeypatch):
    lines = [
        "event: metadata",
        'data: {"message_id": "m1", "pii_score": 0.2}',
        "",
        "data: hi",
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    seen = []
    list(chat.stream_tokens("sid-1", on_metadata=seen.append))
    assert seen == [{"message_id": "m1", "pii_score": 0.2}]


def test_get_pending_metadata_returns_copy(monkeypatch):
    lines = [
        "event: metadata",
        'data: {"message_id": "m1", "pii_score": 0.1}',
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_metadata()
    list(chat.stream_tokens("sid-1"))
    metadata = chat.get_pending_metadata()
    metadata[0]["pii_score"] = 0.99
    assert chat.get_pending_metadata()[0]["pii_score"] == 0.1


def test_clear_pending_metadata_resets_buffer(monkeypatch):
    lines = [
        "event: metadata",
        'data: {"message_id": "m1", "pii_score": 0.1}',
        "",
        "event: done",
        "data: {}",
        "",
    ]
    monkeypatch.setattr(chat.httpx, "stream", lambda *a, **k: FakeStreamResponse(lines))
    chat.clear_pending_metadata()
    list(chat.stream_tokens("sid-1"))
    assert len(chat.get_pending_metadata()) == 1
    chat.clear_pending_metadata()
    assert chat.get_pending_metadata() == []


def test_agent_service_url_default():
    assert chat.agent_service_url() == "http://localhost:8000"


def test_agent_service_url_from_env(monkeypatch):
    monkeypatch.setenv(chat.AGENT_SERVICE_URL_ENV, "http://agent:8123/")
    assert chat.agent_service_url() == "http://agent:8123"


def test_send_message_posts_to_chat_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return "ok"

    monkeypatch.setattr(chat.httpx, "post", fake_post)
    assert chat.send_message("sid-1", "hi") == "ok"
    assert captured["url"] == "http://localhost:8000/sessions/sid-1/chat"
    assert captured["json"] == {"message": "hi"}
