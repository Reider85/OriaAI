"""Unit tests for C-6 session runtime context + forensic cancel fields."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from llm_client.agent.service import (
    _content_byte_size,
    _seed_runtime_from_state,
    _update_runtime_from_chunk,
)
from llm_client.transport.runtime_context import (
    SessionRuntimeContext,
    SessionRuntimeRegistry,
    extract_forensic_fields,
    get_runtime_registry,
    load_runtime_context,
    runtime_context_key,
    save_runtime_context,
)
from llm_client.transport.subscriber import CancelSubscriber


class FakeRedis:
    def __init__(self, messages=None):
        self._messages = list(messages or [])
        self.store: dict[str, str] = {}
        self.published = []

    async def publish(self, channel, message):
        self.published.append((channel, message))

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)

    def pubsub(self):
        return FakePubSub(self._messages)


class FakePubSub:
    def __init__(self, messages):
        self._messages = list(messages)

    def listen(self):
        async def gen():
            for m in self._messages:
                yield m

        return gen()

    async def subscribe(self, channel):
        self.channel = channel

    async def unsubscribe(self, channel):
        pass

    async def aclose(self):
        pass


async def drain_tasks():
    import asyncio

    for _ in range(100):
        await asyncio.sleep(0.01)


def test_runtime_context_roundtrip():
    ctx = SessionRuntimeContext(
        last_node_executed="planner",
        messages_count=3,
        partial_answer_size_bytes=42,
    )
    restored = SessionRuntimeContext.from_dict(ctx.to_dict())
    assert restored == ctx


def test_extract_forensic_fields_normalises_types():
    fields = extract_forensic_fields(
        {
            "last_node_executed": "final_answer",
            "messages_count": "5",
            "partial_answer_size_bytes": True,
        }
    )
    assert fields["last_node_executed"] == "final_answer"
    assert fields["messages_count"] is None
    assert fields["partial_answer_size_bytes"] is None


def test_registry_update_and_clear():
    registry = SessionRuntimeRegistry()
    registry.update("s1", last_node_executed="planner", messages_count=1)
    registry.update("s1", messages_count=2)
    ctx = registry.get("s1")
    assert ctx is not None
    assert ctx.last_node_executed == "planner"
    assert ctx.messages_count == 2
    registry.clear("s1")
    assert registry.get("s1") is None


def test_get_runtime_registry_singleton():
    assert get_runtime_registry() is get_runtime_registry()


@pytest.mark.asyncio
async def test_save_and_load_runtime_context_redis_roundtrip():
    redis = FakeRedis()
    ctx = SessionRuntimeContext(
        last_node_executed="tool_executor",
        messages_count=4,
        partial_answer_size_bytes=128,
    )
    await save_runtime_context(redis, "sess-9", ctx)
    loaded = await load_runtime_context(redis, "sess-9")
    assert loaded == ctx.to_dict()
    assert runtime_context_key("sess-9") in redis.store


@pytest.mark.asyncio
async def test_load_runtime_context_missing_returns_none():
    redis = FakeRedis()
    assert await load_runtime_context(redis, "nope") is None
    assert await load_runtime_context(None, "nope") is None


def test_seed_runtime_from_initial_state():
    state = {
        "messages": [
            HumanMessage("hello"),
            AIMessage("partial answer content"),
        ]
    }
    runtime, seen = _seed_runtime_from_state(state)
    assert runtime.messages_count == 2
    assert runtime.partial_answer_size_bytes == _content_byte_size("partial answer content")
    assert len(seen) == 2


def test_update_runtime_from_chunk_tracks_node_and_messages():
    runtime = SessionRuntimeContext()
    seen: set[str] = set()
    chunk = {
        "planner": {
            "messages": [AIMessage("hello from model")],
            "iteration": 1,
        }
    }
    _update_runtime_from_chunk(runtime, chunk, seen)
    assert runtime.last_node_executed == "planner"
    assert runtime.messages_count == 1
    assert runtime.partial_answer_size_bytes == len(b"hello from model")


def test_update_runtime_from_final_answer_chunk():
    runtime = SessionRuntimeContext(messages_count=2)
    seen = {"a", "b"}
    chunk = {"final_answer": {"final_answer": "final text", "messages": []}}
    _update_runtime_from_chunk(runtime, chunk, seen)
    assert runtime.last_node_executed == "final_answer"
    assert runtime.partial_answer_size_bytes == len(b"final text")


def test_update_runtime_ignores_control_chunks():
    runtime = SessionRuntimeContext(last_node_executed="planner", messages_count=1)
    seen = set()
    _update_runtime_from_chunk(runtime, {"_error": RuntimeError("x")}, seen)
    assert runtime.last_node_executed == "planner"


@pytest.mark.asyncio
async def test_cancel_event_populates_forensic_fields_from_provider():
    from llm_client.transport.cancel import CancellationTokenRegistry

    captured = {}
    registry = CancellationTokenRegistry()
    registry.register("s1")
    msg = {
        "type": "message",
        "data": json.dumps({"reason": "user_cancelled", "user_id": "u1"}),
    }
    fake = FakeRedis(messages=[msg])

    runtime_registry = get_runtime_registry()
    runtime_registry.update(
        "s1",
        last_node_executed="tool_executor",
        messages_count=6,
        partial_answer_size_bytes=256,
    )

    async def handler(event):
        captured.update(event)

    def provider(session_id: str):
        ctx = runtime_registry.get(session_id)
        return ctx.to_dict() if ctx else None

    sub = CancelSubscriber(
        fake,
        registry,
        cancel_event_handler=handler,
        session_context_provider=provider,
    )
    await sub.subscribe("s1")
    await drain_tasks()

    assert captured["event_type"] == "session_cancelled"
    assert captured["last_node_executed"] == "tool_executor"
    assert captured["messages_count"] == 6
    assert captured["partial_answer_size_bytes"] == 256
    runtime_registry.clear("s1")
    await sub.unsubscribe("s1")


@pytest.mark.asyncio
async def test_cancel_event_populates_forensic_fields_from_redis():
    from llm_client.transport.cancel import CancellationTokenRegistry

    captured = {}
    registry = CancellationTokenRegistry()
    registry.register("s2")
    msg = {
        "type": "message",
        "data": json.dumps({"reason": "timeout"}),
    }
    fake = FakeRedis(messages=[msg])
    await save_runtime_context(
        fake,
        "s2",
        {
            "last_node_executed": "rag_retriever",
            "messages_count": 3,
            "partial_answer_size_bytes": 99,
        },
    )

    async def handler(event):
        captured.update(event)

    sub = CancelSubscriber(fake, registry, cancel_event_handler=handler)
    await sub.subscribe("s2")
    await drain_tasks()

    assert captured["last_node_executed"] == "rag_retriever"
    assert captured["messages_count"] == 3
    assert captured["partial_answer_size_bytes"] == 99
    await sub.unsubscribe("s2")


@pytest.mark.asyncio
async def test_cancel_event_still_emits_without_runtime_context():
    from llm_client.transport.cancel import CancellationTokenRegistry

    captured = {}
    registry = CancellationTokenRegistry()
    registry.register("s3")
    msg = {
        "type": "message",
        "data": json.dumps({"reason": "system_error"}),
    }
    fake = FakeRedis(messages=[msg])

    async def handler(event):
        captured.update(event)

    sub = CancelSubscriber(fake, registry, cancel_event_handler=handler)
    await sub.subscribe("s3")
    await drain_tasks()

    assert captured["last_node_executed"] is None
    assert captured["messages_count"] is None
    assert captured["partial_answer_size_bytes"] is None
    assert captured["event_type"] == "session_cancelled"
    await sub.unsubscribe("s3")


@pytest.mark.asyncio
async def test_provider_error_falls_back_to_redis():
    from llm_client.transport.cancel import CancellationTokenRegistry

    captured = {}
    registry = CancellationTokenRegistry()
    registry.register("s4")
    msg = {"type": "message", "data": json.dumps({"reason": "hidden"})}
    fake = FakeRedis(messages=[msg])
    await save_runtime_context(
        fake,
        "s4",
        {"last_node_executed": "planner", "messages_count": 2, "partial_answer_size_bytes": 10},
    )

    def broken_provider(_sid):
        raise RuntimeError("provider down")

    async def handler(event):
        captured.update(event)

    sub = CancelSubscriber(
        fake,
        registry,
        cancel_event_handler=handler,
        session_context_provider=broken_provider,
    )
    await sub.subscribe("s4")
    await drain_tasks()

    assert captured["last_node_executed"] == "planner"
    assert captured["messages_count"] == 2
    await sub.unsubscribe("s4")
