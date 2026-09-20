import json

import pytest

from llm_client.transport.cancel import CancellationTokenRegistry
from llm_client.transport.publisher import CancelPublisher
from llm_client.transport.subscriber import CancelSubscriber


class FakeRedis:
    def __init__(self, messages):
        self._messages = list(messages)
        self.published = []

    async def publish(self, channel, message):
        self.published.append((channel, message))

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
    """Give background listener tasks a chance to run."""
    import asyncio

    for _ in range(100):
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_cancel_event_handler_receives_full_event():
    captured = {}
    registry = CancellationTokenRegistry()
    registry.register("s1")
    msg = {
        "type": "message",
        "data": json.dumps({"reason": "timeout", "user_id": "u-42", "timestamp": "t"}),
    }
    fake = FakeRedis(messages=[msg])

    async def handler(event):
        captured.update(event)

    sub = CancelSubscriber(fake, registry, cancel_event_handler=handler)
    await sub.subscribe("s1")
    await drain_tasks()

    assert captured["event_type"] == "session_cancelled"
    assert captured["session_id"] == "s1"
    assert captured["reason"] == "timeout"
    assert captured["user_id"] == "u-42"
    assert captured["duration_ms"] >= 0
    assert "timestamp" in captured
    await sub.unsubscribe("s1")


@pytest.mark.asyncio
async def test_cancel_event_fires_once_per_cancel():
    events = []
    registry = CancellationTokenRegistry()
    registry.register("s1")
    msg = {
        "type": "message",
        "data": json.dumps({"reason": "user_cancelled"}),
    }
    fake = FakeRedis(messages=[msg])

    async def handler(event):
        events.append(event)

    sub = CancelSubscriber(fake, registry, cancel_event_handler=handler)
    await sub.subscribe("s1")
    await drain_tasks()
    # The listener breaks after the first message; exactly one cancel event.
    assert len(events) == 1
    await sub.unsubscribe("s1")


@pytest.mark.asyncio
async def test_duplicate_cancel_does_not_double_emit():
    events = []
    registry = CancellationTokenRegistry()
    registry.register("s1")
    msg = {
        "type": "message",
        "data": json.dumps({"reason": "user_cancelled"}),
    }
    fake = FakeRedis(messages=[msg, msg])
    sub = CancelSubscriber(fake, registry, cancel_event_handler=lambda e: events.append(e))
    await sub.subscribe("s1")
    await drain_tasks()
    assert len(events) == 1
    await sub.unsubscribe("s1")


@pytest.mark.asyncio
async def test_handler_error_does_not_break_cancel():
    token = None
    registry = CancellationTokenRegistry()
    token = registry.register("s1")
    msg = {
        "type": "message",
        "data": json.dumps({"reason": "system_error"}),
    }
    fake = FakeRedis(messages=[msg])

    async def boom(event):
        raise RuntimeError("logging backend down")

    sub = CancelSubscriber(fake, registry, cancel_event_handler=boom)
    await sub.subscribe("s1")
    await drain_tasks()
    # Even though the handler failed, the token must still be cancelled.
    assert token.is_cancelled
    assert token.reason == "system_error"
    await sub.unsubscribe("s1")


@pytest.mark.asyncio
async def test_malformed_message_still_cancels_token():
    registry = CancellationTokenRegistry()
    token = registry.register("s1")
    msg = {"type": "message", "data": "not-json{{"}
    fake = FakeRedis(messages=[msg])
    sub = CancelSubscriber(fake, registry, cancel_event_handler=None)
    await sub.subscribe("s1")
    await drain_tasks()
    assert token.is_cancelled
    assert token.reason == "unknown"
    await sub.unsubscribe("s1")


@pytest.mark.asyncio
async def test_publisher_message_roundtrips_to_subscriber():
    """End-to-end publisher->subscriber without real Redis (contract test)."""

    class LoopbackRedis(FakeRedis):
        def __init__(self):
            super().__init__(messages=[])
            self._subscribers = []

        async def publish(self, channel, message):
            self.published.append((channel, message))
            for sub in self._subscribers:
                if sub.channel == channel:
                    sub._messages.append(
                        {"type": "message", "data": message}
                    )

        def pubsub(self):
            ps = FakePubSub(self._messages)
            self._subscribers.append(ps)
            return ps

    registry = CancellationTokenRegistry()
    token = registry.register("s1")
    redis = LoopbackRedis()
    pub = CancelPublisher(redis)
    sub = CancelSubscriber(redis, registry)
    await sub.subscribe("s1")
    await pub.publish("s1", "user_cancelled", user_id="u1")
    await drain_tasks()
    assert token.is_cancelled
    assert token.reason == "user_cancelled"
    await sub.unsubscribe("s1")