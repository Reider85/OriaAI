"""Factory for creating checkpointers for ADR-010."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import asyncpg
import redis.asyncio as aioredis

from ...config import Settings
from .composite import RedisPostgresCheckpointer
from .metrics import CheckpointMetrics, NullCheckpointMetrics
from .postgres_checkpointer import PostgresCheckpointer
from .redis_checkpointer import RedisCheckpointer

logger = logging.getLogger(__name__)

# UUID namespace for stable thread_id generation
_CHECKPOINT_THREAD_NAMESPACE = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


@dataclass
class CheckpointerBundle:
    """Bundle containing the checkpointer and its resources.

    Attributes:
        checkpointer: The main checkpointer (composite or single-layer)
        redis_client: Redis client (if created, None for postgres_only)
        pg_pool: PostgreSQL connection pool (if created, None for redis_only)
        postgres_checkpointer: PostgreSQL checkpointer (if created, None for redis_only)
        backend: The backend that was actually created
        owns_pg_pool: True when this factory created pg_pool and must close it
    """

    checkpointer: Any
    redis_client: aioredis.Redis | None
    pg_pool: asyncpg.Pool | None
    postgres_checkpointer: PostgresCheckpointer | None
    backend: str
    owns_pg_pool: bool = True


def build_checkpointer(
    settings: Settings,
    *,
    operational_writer: Any | None = None,
    on_total_failure: Any | None = None,
    pg_pool: asyncpg.Pool | None = None,
) -> CheckpointerBundle:
    """Build a checkpointer based on the configured backend.

    Args:
        settings: Application settings with checkpoint backend configuration
        operational_writer: Optional operational writer for logging events
        on_total_failure: Optional callback for when both layers fail
        pg_pool: Optional existing asyncpg pool to reuse (shared app pool).
            When provided the caller owns its lifecycle — this factory will
            not close it.

    Returns:
        CheckpointerBundle containing the checkpointer and its resources

    Raises:
        ValueError: If the backend is invalid or required dependencies are missing
    """
    backend = settings.checkpoint_backend

    # Initialize resources as None
    redis_client = None
    owns_pg_pool = pg_pool is None
    postgres_checkpointer = None
    checkpointer: Any = None

    # Create metrics
    metrics = CheckpointMetrics() if settings.environment != "test" else NullCheckpointMetrics()

    try:
        if backend in {"redis_postgres", "redis_only"}:
            # Create Redis client for checkpoint DB
            redis_client = aioredis.from_url(
                settings.redis_checkpoint_url,
                decode_responses=False,  # We need bytes for hex encoding
            )

            # Test connection
            loop = asyncio.get_event_loop()
            try:
                loop.run_until_complete(redis_client.ping())
            except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001
                logger.warning("Redis checkpoint connection failed: %s", exc)
                redis_client = None  # Fall through to postgres_only if available

        if backend in {"redis_postgres", "postgres_only"}:
            if pg_pool is None:
                # Create PostgreSQL connection pool (async — must be awaited)
                pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
                pg_pool = asyncio.get_event_loop().run_until_complete(
                    asyncpg.create_pool(
                        pg_url,
                        min_size=1,
                        max_size=5,
                        command_timeout=60,
                    )
                )

                # Test connection
                loop = asyncio.get_event_loop()
                try:
                    conn = loop.run_until_complete(pg_pool.acquire())
                    loop.run_until_complete(pg_pool.release(conn))
                except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001
                    logger.warning("PostgreSQL checkpoint connection failed: %s", exc)
                    loop.run_until_complete(pg_pool.close())
                    pg_pool = None  # Fall through to redis_only if available
            else:
                logger.info("Reusing injected pg_pool for checkpointing")

        # Create the appropriate checkpointer based on what succeeded
        if backend == "redis_postgres" and redis_client and pg_pool:
            # Composite checkpointer
            redis_cp = RedisCheckpointer(
                redis_client=redis_client,
                ttl_seconds=settings.redis_checkpoint_ttl_seconds,
            )
            pg_cp = PostgresCheckpointer(
                pg_pool=pg_pool,
                flush_interval_seconds=settings.checkpoint_flush_interval_seconds,
                flush_batch_size=settings.checkpoint_flush_batch_size,
                metrics=metrics,
            )
            checkpointer = RedisPostgresCheckpointer(
                redis_checkpointer=redis_cp,
                postgres_checkpointer=pg_cp,
                metrics=metrics,
                operational_writer=operational_writer,
                on_total_failure=on_total_failure,
            )
            logger.info("Created RedisPostgresCheckpointer (composite)")

        elif backend == "redis_only" and redis_client:
            # Redis-only checkpointer
            checkpointer = RedisCheckpointer(
                redis_client=redis_client,
                ttl_seconds=settings.redis_checkpoint_ttl_seconds,
                metrics=metrics,
            )
            logger.info("Created RedisCheckpointer (redis_only)")

        elif backend == "postgres_only" and pg_pool:
            # PostgreSQL-only checkpointer
            postgres_checkpointer = PostgresCheckpointer(
                pg_pool=pg_pool,
                flush_interval_seconds=settings.checkpoint_flush_interval_seconds,
                flush_batch_size=settings.checkpoint_flush_batch_size,
                metrics=metrics,
            )
            checkpointer = postgres_checkpointer
            logger.info("Created PostgresCheckpointer (postgres_only)")

        else:
            # Fallback: no checkpointer available
            logger.warning(
                "No checkpoint backend available. Falling back to no checkpointing. "
                "Backend=%s, Redis=%s, PG=%s",
                backend,
                bool(redis_client),
                bool(pg_pool),
            )
            checkpointer = None
            # Clear resources to avoid leaks (only if we own them)
            if redis_client:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(redis_client.aclose())
                redis_client = None
            if pg_pool and owns_pg_pool:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(pg_pool.close())
                pg_pool = None
            postgres_checkpointer = None

        return CheckpointerBundle(
            checkpointer=checkpointer,
            redis_client=redis_client,
            pg_pool=pg_pool,
            postgres_checkpointer=postgres_checkpointer,
            backend=backend,
            owns_pg_pool=owns_pg_pool,
        )

    except Exception as exc:
        # Clean up resources on error (only pools/clients we created)
        logger.error("Failed to build checkpointer: %s", exc)
        if redis_client:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(redis_client.aclose())
        if pg_pool and owns_pg_pool:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(pg_pool.close())
        raise


def generate_thread_id(session_id: str) -> str:
    """Generate a stable thread_id from session_id using UUID5.

    Args:
        session_id: Session identifier (from API path)

    Returns:
        UUID string suitable for use as thread_id in checkpoint storage
    """
    import uuid

    return str(uuid.uuid5(uuid.UUID(_CHECKPOINT_THREAD_NAMESPACE), session_id))
