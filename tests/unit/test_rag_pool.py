"""Unit tests for shared pg_pool resolution helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_client.config import Settings
from llm_client.rag import pool as pool_mod


def _settings() -> Settings:
    return Settings(
        environment="dev",
        openai_api_key="sk-test",
        llm_provider="openai",
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/llm_client",
    )


@pytest.fixture(autouse=True)
def _reset_pool():
    pool_mod._pool = None
    pool_mod._pool_settings = None
    yield
    pool_mod._pool = None
    pool_mod._pool_settings = None


def test_resolve_pool_prefers_attribute():
    fake = MagicMock()
    settings = MagicMock()
    settings.pg_pool = fake
    assert pool_mod.resolve_pool(settings) is fake


def test_resolve_pool_returns_none_without_singleton():
    settings = _settings()
    assert pool_mod.resolve_pool(settings) is None


def test_resolve_pool_uses_shared_singleton():
    marker = MagicMock()
    marker.is_closed.return_value = False
    pool_mod._pool = marker
    settings = _settings()
    assert pool_mod.resolve_pool(settings) is marker


@pytest.mark.asyncio
async def test_get_shared_pool_creates_and_reuses():
    settings = _settings()
    fake_pool = MagicMock()
    fake_pool.is_closed.return_value = False

    with patch("asyncpg.create_pool", new=AsyncMock(return_value=fake_pool)) as create:
        p1 = await pool_mod.get_shared_pool(settings)
        p2 = await pool_mod.get_shared_pool(settings)

    assert p1 is fake_pool
    assert p2 is fake_pool
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_close_shared_pool():
    fake_pool = MagicMock()
    fake_pool.is_closed.return_value = False
    fake_pool.close = AsyncMock()
    pool_mod._pool = fake_pool

    await pool_mod.close_shared_pool()

    fake_pool.close.assert_awaited_once()
    assert pool_mod._pool is None
