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
