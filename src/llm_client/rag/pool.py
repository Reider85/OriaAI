"""Shared asyncpg pool singleton for RAG + checkpointing (ADR-010 / ADR-020)."""

import logging
from typing import Any

import asyncpg

from llm_client.config import Settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_settings: Settings | None = None


def _normalize_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def get_shared_pool(settings: Settings | None = None) -> asyncpg.Pool:
    """Return the process-wide asyncpg pool, creating it on first use.

    The caller does NOT own the pool — close it via ``close_shared_pool()``
    during application shutdown.
    """
    global _pool, _pool_settings

    if _pool is not None and not _pool.is_closed():
        return _pool

    if settings is None:
        from llm_client.config import settings as default_settings

        settings = default_settings

    _pool = await asyncpg.create_pool(
        _normalize_url(settings.database_url),
        min_size=1,
        max_size=5,
        command_timeout=60,
    )
    _pool_settings = settings
    logger.info("Shared pg_pool created for %s", settings.database_url.split("@")[-1])
    return _pool


async def close_shared_pool() -> None:
    """Close the shared pool if one was created. Safe to call repeatedly."""
    global _pool, _pool_settings
    if _pool is not None and not _pool.is_closed():
        await _pool.close()
        logger.info("Shared pg_pool closed")
    _pool = None
    _pool_settings = None


def get_shared_pool_sync() -> asyncpg.Pool | None:
    """Return the shared pool if it already exists, else None."""
    if _pool is not None and not _pool.is_closed():
        return _pool
    return None


def resolve_pool(app_settings: Any = None) -> asyncpg.Pool | None:
    """Best-effort pool lookup for pipeline/tool call sites.

    Order: explicit ``app_settings.pg_pool`` attribute → shared singleton →
    None. Never creates a pool (avoids surprise I/O on the request path).
    """
    pool = getattr(app_settings, "pg_pool", None)
    if pool is not None and hasattr(pool, "acquire"):
        return pool
    return get_shared_pool_sync()
