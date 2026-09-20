import json

import pytest

from llm_client.transport.cancel import CancellationTokenRegistry
from llm_client.transport.publisher import CancelPublisher
from llm_client.transport.subscriber import CancelSubscriber


class FakeRedis:
    """Minimal stand-in for redis.asyncio.Redis used to capture publish calls."""

    def __init__(self):
        self.published = []

    async def publish(self, channel, message):
        self.published.append((channel, message))


class FakePubSub:
    def __init__(self, messages):
        self._messages = list(messages)
        self.closed = False
        self.unsubscribed = []

    def listen(self):
        async def gen():
            for m in self._messages:
                yield m

        return gen()

    async def subscribe(self, channel):
        self.channel = channel

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def close(self):
        self.closed = True


class FakeRedisPubsub(FakeRedis):
    def __init__(self, messages=None):
        super().__init__()
        self._messages = messages or []
        self.created = []

    def pubsub(self):
        ps = FakePubSub(self._messages)
        self.created.append(ps)
        return ps


@pytest.mark.asyncio
async def test_publisher_message_format():
    fake = FakeRedis()
    pub = CancelPublisher(fake)
    await pub.publish("s1", "user_cancelled", user_id="u1")
    channel, message = fake.published[0]
    assert channel == "session:s1:cancel"
    data = json.loads(message)
    assert data["reason"] == "user_cancelled"
    assert data["user_id"] == "u1"
    assert data["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_publisher_retries_then_raises():
    class FlakyRedis:
        def __init__(self):
            self.attempts = 0

        async def publish(self, channel, message):
            self.attempts += 1
            raise ConnectionError("down")

    fake = FlakyRedis()
    pub = CancelPublisher(fake)
    from llm_client.transport.publisher import PublishError

    with pytest.raises(PublishError):
        await pub.publish("s1", "timeout")
    assert fake.attempts == 5  # 1 initial + 4 retries


@pytest.mark.asyncio
async def test_subscriber_cancels_token():
    registry = CancellationTokenRegistry()
    token = registry.register("s1")
    msg = {"type": "message", "data": json.dumps({"reason": "timeout", "timestamp": "now"})}
    fake = FakeRedisPubsub(messages=[msg])
    sub = CancelSubscriber(fake, registry)
    await sub.subscribe("s1")
    for _ in range(50):
        if token.is_cancelled:
            break
        await asyncio_sleep()
    assert token.is_cancelled
    assert token.reason == "timeout"
    await sub.unsubscribe("s1")


@pytest.mark.asyncio
async def test_subscriber_ignores_after_completion():
    registry = CancellationTokenRegistry()
    sub = CancelSubscriber(FakeRedisPubsub(), registry)
    await sub.subscribe("s1")
    await sub.unsubscribe("s1")
    # No token was cancelled; task cleaned up.
    assert "s1" not in sub._tasks


def asyncio_sleep():
    import asyncio

    return asyncio.sleep(0.01)