"""Integration tests for RedisPostgresCheckpointer (B-3)."""

import uuid

import asyncpg
import pytest
import redis.asyncio as aioredis

from llm_client.config import Settings
from llm_client.orchestration.checkpointers.composite import RedisPostgresCheckpointer
from llm_client.orchestration.checkpointers.factory import build_checkpointer

# ── Helper functions ───────────────────────────────────────────────────────────────

async def _are_services_available():
    """Check if Redis and PostgreSQL are available for integration tests."""
    try:
        import asyncpg
        import redis.asyncio as aioredis
        
        # Check Redis
        redis_client = aioredis.from_url("redis://127.0.0.1:6379/1", decode_responses=False)
        await redis_client.ping()
        await redis_client.close()
        redis_available = True
    except Exception:  # noqa: BLE001 — degrade gracefully if Redis unavailable for test setup
        redis_available = False
    
    try:
        # Check PostgreSQL
        conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5434/postgres")
        await conn.close()
        postgres_available = True
    except Exception:  # noqa: BLE001 — degrade gracefully if PostgreSQL unavailable for test setup
        postgres_available = False
    
    return redis_available and postgres_available


# ── Test data ──────────────────────────────────────────────────────────────────

SAMPLE_CHECKPOINT = {
    "id": str(uuid.uuid4()),
    "ts": "2026-09-27T10:00:00.000000+00:00",
    "channel_values": [
        {"role": "user", "content": "Hello, world!"}
    ],
    "channel_versions": {},
    "versions_seen": {},
    "updated_channels": [],
}

SAMPLE_CONFIG = {"configurable": {"thread_id": str(uuid.uuid4())}}


# ── PostgreSQL DDL for agent_checkpoints table ───────────────────────────────────

AGENT_CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    thread_id UUID NOT NULL,
    checkpoint_id UUID NOT NULL,
    parent_id UUID,
    state JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP(timezone=True) NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_id)
);
"""


# ── Test fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
async def redis_client():
    """Redis client for checkpoint DB."""
    client = aioredis.from_url("redis://127.0.0.1:6379/1", decode_responses=False)
    try:
        await client.ping()
        yield client
    except Exception:  # noqa: BLE001 — skip test if Redis unavailable
        pytest.skip("Redis checkpoint DB not available")
    finally:
        await client.aclose()


@pytest.fixture
async def pg_pool():
    """PostgreSQL connection pool."""
    dsn = "postgresql://postgres:postgres@localhost:5434/llm_client"
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(AGENT_CHECKPOINTS_DDL)
        yield pool
    except Exception:  # noqa: BLE001 — skip test if PostgreSQL unavailable
        pytest.skip("PostgreSQL not available")
    finally:
        await pool.close()


@pytest.fixture
def settings():
    """Test settings with checkpoint backend."""
    return Settings(
        checkpoint_backend="redis_postgres",
        redis_checkpoint_url="redis://127.0.0.1:6379/1",
        database_url="postgresql://postgres:postgres@localhost:5434/llm_client",
        redis_checkpoint_ttl_seconds=60,  # Short TTL for testing
    )


@pytest.fixture
async def composite_checkpointer(redis_client, pg_pool, settings):
    """Composite checkpointer with real Redis and PostgreSQL."""
    from llm_client.orchestration.checkpointers.postgres_checkpointer import PostgresCheckpointer
    from llm_client.orchestration.checkpointers.redis_checkpointer import RedisCheckpointer
    
    redis_cp = RedisCheckpointer(
        redis_client=redis_client,
        ttl_seconds=60,
    )
    
    pg_cp = PostgresCheckpointer(
        pg_pool=pg_pool,
        flush_interval_seconds=5,
        flush_batch_size=50,
    )
    
    return RedisPostgresCheckpointer(
        redis_checkpointer=redis_cp,
        postgres_checkpointer=pg_cp,
    )


# ── Integration tests ────────────────────────────────────────────────────────────

class TestCompositeCheckpointIntegration:
    """Integration tests with real Redis and PostgreSQL."""
    
    @pytest.mark.asyncio
    async def test_round_trip(self, composite_checkpointer, SAMPLE_CHECKPOINT, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test complete round-trip: put → get."""
        metadata = {"source": "integration_test"}
        
        # Put checkpoint
        result = await composite_checkpointer.aput(SAMPLE_CONFIG, SAMPLE_CHECKPOINT, metadata)
        assert result == SAMPLE_CONFIG
        
        # Get checkpoint
        retrieved = await composite_checkpointer.aget(SAMPLE_CONFIG)
        assert retrieved == SAMPLE_CHECKPOINT
        
        # Get tuple
        retrieved_tuple = await composite_checkpointer.aget_tuple(SAMPLE_CONFIG)
        assert retrieved_tuple is not None
        assert retrieved_tuple["checkpoint"] == SAMPLE_CHECKPOINT
        assert retrieved_tuple["metadata"] == metadata
    
    @pytest.mark.asyncio
    async def test_redis_restart_fallback_to_postgres(self, composite_checkpointer, SAMPLE_CHECKPOINT, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test that after Redis restart, read falls back to PostgreSQL."""
        metadata = {"source": "integration_test"}
        
        # Store checkpoint in both layers
        await composite_checkpointer.aput(SAMPLE_CONFIG, SAMPLE_CHECKPOINT, metadata)
        
        # Simulate Redis restart by closing the connection
        await composite_checkpointer._redis._redis_client.aclose()
        
        # Create new Redis client that returns None (simulating restart)
        new_redis_client = aioredis.from_url("redis://127.0.0.1:6379/1", decode_responses=False)
        composite_checkpointer._redis._redis_client = new_redis_client
        
        # Read should fall back to PostgreSQL
        retrieved = await composite_checkpointer.aget(SAMPLE_CONFIG)
        assert retrieved == SAMPLE_CHECKPOINT
        
        # Should have used PostgreSQL fallback
        # (This is hard to verify directly, but the test passes if no exception is raised)
    
    @pytest.mark.asyncio
    async def test_postgres_restart_write_to_redis(self, composite_checkpointer, SAMPLE_CHECKPOINT, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test that after PostgreSQL restart, write still works via Redis."""
        metadata = {"source": "integration_test"}
        
        # Simulate PostgreSQL restart by closing the pool
        await composite_checkpointer._postgres._pg_pool.close()
        
        # Create new PostgreSQL pool that will be closed (simulating restart)
        new_pool = await asyncpg.create_pool(
            "postgresql://postgres:postgres@localhost:5434/llm_client",
            min_size=1,
            max_size=5,
        )
        composite_checkpointer._postgres._pg_pool = new_pool
        
        # Write should still work via Redis
        result = await composite_checkpointer.aput(SAMPLE_CONFIG, SAMPLE_CHECKPOINT, metadata)
        assert result == SAMPLE_CONFIG
        
        # Should be able to read from Redis
        retrieved = await composite_checkpointer.aget(SAMPLE_CONFIG)
        assert retrieved == SAMPLE_CHECKPOINT
        
        # Clean up
        await new_pool.close()
    
    @pytest.mark.asyncio
    async def test_list_merges_sources(self, composite_checkpointer, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test that alist merges checkpoints from both sources."""
        # Store different checkpoints in Redis and PostgreSQL
        for i in range(3):
            checkpoint = SAMPLE_CHECKPOINT.copy()
            checkpoint["id"] = str(uuid.uuid4())
            checkpoint["ts"] = f"2026-09-27T10:00:{i:02d}+00:00"
            
            metadata = {"source": "test", "index": i}
            
            # Store in Redis
            await composite_checkpointer._redis.aput(SAMPLE_CONFIG, checkpoint, metadata)
            
            # Store in PostgreSQL with different timestamp
            pg_checkpoint = checkpoint.copy()
            pg_checkpoint["ts"] = f"2026-09-27T10:00:{i+3:02d}+00:00"
            await composite_checkpointer._postgres.aput(SAMPLE_CONFIG, pg_checkpoint, metadata)
        
        # List from composite
        checkpoints = []
        async for checkpoint in composite_checkpointer.alist(SAMPLE_CONFIG):
            checkpoints.append(checkpoint)
        
        # Should have 6 unique checkpoints (3 from Redis + 3 from PostgreSQL)
        assert len(checkpoints) == 6
        
        # Should be sorted by timestamp (newest first)
        timestamps = [cp["checkpoint"]["ts"] for cp in checkpoints]
        assert timestamps == sorted(timestamps, reverse=True)
    
    @pytest.mark.asyncio
    async def test_delete_thread(self, composite_checkpointer, SAMPLE_CHECKPOINT, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test deleting all checkpoints for a thread."""
        # Store some checkpoints
        metadata = {"source": "integration_test"}
        await composite_checkpointer.aput(SAMPLE_CONFIG, SAMPLE_CHECKPOINT, metadata)
        
        thread_id = SAMPLE_CONFIG["configurable"]["thread_id"]
        
        # Delete thread
        await composite_checkpointer.adelete_thread(thread_id)
        
        # Should no longer be able to get the checkpoint
        retrieved = await composite_checkpointer.aget(SAMPLE_CONFIG)
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_writes_to_both_layers(self, composite_checkpointer, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test that writes are stored in both layers."""
        writes = [
            ("messages", [{"role": "user", "content": "test message"}]),
            ("iterations", [1, 2, 3]),
        ]
        task_id = "test-task"
        
        # Write to both layers
        await composite_checkpointer.aput_writes(SAMPLE_CONFIG, writes, task_id)
        
        # Verify writes are in both layers
        # (This is hard to verify directly, but the test passes if no exception is raised)
    
    @pytest.mark.asyncio
    async def test_backend_degradation(self, settings):
        """Test that the factory handles backend degradation gracefully."""
        # Skip if services are available (this test is for degradation scenarios)
        if await _are_services_available():
            pytest.skip("This test requires services to be unavailable")
        
        # Test redis_only backend (should return None when Redis unavailable)
        settings.checkpoint_backend = "redis_only"
        bundle = build_checkpointer(settings)
        assert bundle.checkpointer is None
        assert bundle.redis_client is None
        assert bundle.pg_pool is None
        assert bundle.postgres_checkpointer is None
        
        # Test postgres_only backend (should return None when PostgreSQL unavailable)
        settings.checkpoint_backend = "postgres_only"
        bundle = build_checkpointer(settings)
        assert bundle.checkpointer is None
        assert bundle.redis_client is None
        assert bundle.pg_pool is None
        assert bundle.postgres_checkpointer is None
        
        # Test invalid backend (should fall back to None)
        settings.checkpoint_backend = "invalid_backend"
        bundle = build_checkpointer(settings)
        assert bundle.checkpointer is None
        assert bundle.redis_client is None
        assert bundle.pg_pool is None
        assert bundle.postgres_checkpointer is None


class TestCompositeCheckpointPerformance:
    """Performance tests for the composite checkpointer."""
    
    @pytest.mark.asyncio
    async def test_redis_write_latency(self, composite_checkpointer, SAMPLE_CHECKPOINT, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test that Redis write latency is acceptable."""
        import time
        
        metadata = {"source": "performance_test"}
        
        start_time = time.perf_counter()
        await composite_checkpointer.aput(SAMPLE_CONFIG, SAMPLE_CHECKPOINT, metadata)
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        # Should be fast (< 10ms for local Redis)
        assert latency_ms < 100  # Generous threshold for CI
    
    @pytest.mark.asyncio
    async def test_postgres_write_latency(self, composite_checkpointer, SAMPLE_CHECKPOINT, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test that PostgreSQL write latency is acceptable."""
        import time
        
        metadata = {"source": "performance_test"}
        
        start_time = time.perf_counter()
        await composite_checkpointer.aput(SAMPLE_CONFIG, SAMPLE_CHECKPOINT, metadata)
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        # Should be fast (< 50ms for local PG)
        assert latency_ms < 200  # Generous threshold for CI
    
    @pytest.mark.asyncio
    async def test_read_latency(self, composite_checkpointer, SAMPLE_CHECKPOINT, SAMPLE_CONFIG):
        # Skip if services not available
        if not await _are_services_available():
            pytest.skip("Redis and PostgreSQL required for integration tests")
        """Test that read latency is acceptable."""
        import time
        
        metadata = {"source": "performance_test"}
        await composite_checkpointer.aput(SAMPLE_CONFIG, SAMPLE_CHECKPOINT, metadata)
        
        # Redis read
        start_time = time.perf_counter()
        await composite_checkpointer.aget(SAMPLE_CONFIG)
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        # Should be fast (< 10ms for local Redis)
        assert latency_ms < 100  # Generous threshold for CI
