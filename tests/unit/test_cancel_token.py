import asyncio

import pytest

from llm_client.transport.cancel import CancellationToken, CancellationTokenRegistry


@pytest.fixture
def registry():
    return CancellationTokenRegistry()


@pytest.mark.asyncio
async def test_token_cancel_sets_reason(registry):
    token = registry.register("s1")
    assert not token.is_cancelled
    token.cancel("user_cancelled")
    assert token.is_cancelled
    assert token.reason == "user_cancelled"


@pytest.mark.asyncio
async def test_double_cancel_keeps_first_reason():
    token = CancellationToken("s1")
    token.cancel("first")
    token.cancel("second")
    assert token.reason == "first"


@pytest.mark.asyncio
async def test_callback_fires_exactly_once():
    token = CancellationToken("s1")
    calls = []

    async def on_cancel():
        calls.append(1)

    token.on_cancel(on_cancel)
    token.cancel("user_cancelled")
    token.cancel("again")
    await asyncio.sleep(0.01)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_callback_registered_after_cancel_fires():
    token = CancellationToken("s1")
    calls = []
    token.cancel("timeout")

    async def on_cancel():
        calls.append(1)

    token.on_cancel(on_cancel)
    await asyncio.sleep(0.01)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_registry_get_unknown_session_is_none(registry):
    assert registry.get("nope") is None


@pytest.mark.asyncio
async def test_registry_cancel(registry):
    registry.register("s1")
    assert registry.cancel("s1", "system_error") is True
    assert registry.cancel("s1", "again") is False


@pytest.mark.asyncio
async def test_registry_cleanup(registry):
    registry.register("s1")
    registry.cleanup("s1")
    assert registry.get("s1") is None
    assert registry.cancel("s1", "x") is False


@pytest.mark.asyncio
async def test_registry_register_returns_distinct_tokens(registry):
    t1 = registry.register("s1")
    t2 = registry.register("s2")
    assert t1 is not t2
    assert registry.get("s1") is t1


@pytest.mark.asyncio
async def test_1000_parallel_cancel_no_race():
    token = CancellationToken("s1")
    await asyncio.gather(*(asyncio.to_thread(token.cancel, "x") for _ in range(1000)))
    assert token.is_cancelled is True
    assert token.reason == "x"


@pytest.mark.asyncio
async def test_wait_returns_true_on_cancel():
    token = CancellationToken("s1")

    async def cancel_soon():
        await asyncio.sleep(0.005)
        token.cancel("timeout")

    asyncio.create_task(cancel_soon())
    assert await token.wait(timeout=1.0) is True


@pytest.mark.asyncio
async def test_wait_timeout_returns_false():
    token = CancellationToken("s1")
    assert await token.wait(timeout=0.005) is False