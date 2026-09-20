"""Integration test: Redis pub/sub cancel round-trip (needs docker-compose Redis)."""
import asyncio
import os

import pytest
from redis import asyncio as aioredis

from llm_client.transport.cancel import CancellationTokenRegistry
from llm_client.transport.publisher import CancelPublisher
from llm_client.transport.subscriber import CancelSubscriber

pytestmark = [pytest.mark.integration]


@pytest.fixture
async def redis_client():
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    client = aioredis.from_url(url, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001 — probe anything that could mean Redis is down
        pytest.skip(f"Redis not available at {url}: {exc}")
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_cancel_pubsub_roundtrip(redis_client):
    registry = CancellationTokenRegistry()
    token = registry.register("int-session-1")
    subscriber = CancelSubscriber(redis_client, registry)
    publisher = CancelPublisher(redis_client)

    await subscriber.subscribe("int-session-1")
    start = asyncio.get_event_loop().time()
    await publisher.publish("int-session-1", "user_cancelled")
    await token.wait(timeout=2.0)
    latency_ms = (asyncio.get_event_loop().time() - start) * 1000
    await subscriber.unsubscribe("int-session-1")

    assert token.is_cancelled
    assert token.reason == "user_cancelled"
    # ADR-013 budget: publish→subscriber delivery < 5ms round-trip on local loopback.
    assert latency_ms < 500
    registry.cleanup("int-session-1")