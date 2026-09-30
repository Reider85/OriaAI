"""Integration tests for the B-5 recovery protocol against real Redis + PostgreSQL.

Covers the four restart/failure scenarios from the B-5 spec. Every test skips
when the backing services are not reachable, so the suite stays green on a
laptop with nothing but docker-compose down.

Scenarios are reproduced by tearing down the *client-side* connection and
rebuilding the composite, which is what a process restart looks like to the
persistence layer. Real ``docker kill`` chaos for the durability budget (B-6)
is a separate staging-only suite.
"""

import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import redis.asyncio as aioredis

from llm_client.orchestration.checkpointers.composite import RedisPostgresCheckpointer
from llm_client.orchestration.checkpointers.postgres_checkpointer import PostgresCheckpointer
from llm_client.orchestration.checkpointers.redis_checkpointer import RedisCheckpointer

REDIS_URL = "redis://127.0.0.1:6379/1"
PG_DSN = "postgresql://postgres:postgres@localhost:5434/llm_client"

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


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_checkpoint(offset_seconds: float = 0.0) -> dict:
    """A valid LangGraph-shaped checkpoint with a distinct, ordered timestamp."""
    ts = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return {
        "id": str(uuid.uuid4()),
        "ts": ts.isoformat(),
        "channel_values": {"messages": ["hello"]},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": [],
    }


def config_for(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def _redis_up() -> bool:
    client = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.ping()
        return True
    except Exception:  # noqa: BLE001 - any driver error means "not reachable"
        return False
    finally:
        await client.aclose()


async def _pg_up() -> bool:
    try:
        conn = await asyncpg.connect(PG_DSN)
    except Exception:  # noqa: BLE001 - any driver error means "not reachable"
        return False
    await conn.close()
    return True


async def _services_ready() -> bool:
    return await _redis_up() and await _pg_up()


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def redis_client():
    if not await _redis_up():
        pytest.skip("Redis checkpoint DB not available")
    client = aioredis.from_url(REDIS_URL, decode_responses=False)
    yield client
    await client.aclose()


@pytest.fixture
async def pg_pool():
    if not await _pg_up():
        pytest.skip("PostgreSQL not available")
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(AGENT_CHECKPOINTS_DDL)
    yield pool
    await pool.close()


@pytest.fixture
def make_composite(redis_client, pg_pool):
    """Build a composite over the live layers; callers own its lifecycle."""

    def _build(*, flush_interval: int = 5, flush_batch: int = 50) -> RedisPostgresCheckpointer:
        return RedisPostgresCheckpointer(
            redis_checkpointer=RedisCheckpointer(redis_client=redis_client, ttl_seconds=120),
            postgres_checkpointer=PostgresCheckpointer(
                pg_pool=pg_pool,
                flush_interval_seconds=flush_interval,
                flush_batch_size=flush_batch,
            ),
        )

    return _build


@pytest.fixture
async def clean_state(redis_client, pg_pool):
    """Truncate PG and flush the Redis checkpoint DB around each test."""
    async with pg_pool.acquire() as conn:
        await conn.execute("TRUNCATE agent_checkpoints")
    await redis_client.flushdb()
    yield
    async with pg_pool.acquire() as conn:
        await conn.execute("TRUNCATE agent_checkpoints")
    await redis_client.flushdb()


# ── Scenario 1: planned restart ──────────────────────────────────────────────


class TestPlannedRestart:
    """Redis and PG both live; PG lags Redis by up to one flush interval."""

    async def test_redis_delta_is_replayed_into_postgres(
        self, make_composite, clean_state
    ):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)

        # Seed the layers the way a live process would: hot write to Redis,
        # snapshot to PG one transition behind, buffer holding the newest.
        composite = make_composite(flush_interval=3600, flush_batch=1000)
        old = make_checkpoint(0)
        new = make_checkpoint(1)

        await composite._redis.aput(cp, old, {"step": 1})
        await composite._postgres.aput(cp, old, {"step": 1})
        await composite._postgres._flush()
        await composite._redis.aput(cp, new, {"step": 2})
        await composite._postgres.aput(cp, new, {"step": 2})

        # A restart discards the in-memory buffer but not either store.
        fresh = make_composite()
        stats = await fresh.recover()

        assert stats["redis_delta_replayed"] == 1
        assert stats["pg_checkpoints_recovered"] == 0

        # After recovery + a flush, PG holds the newest state the graph will see.
        await fresh._postgres._flush()
        row = await fresh._postgres.aget_tuple(cp)
        assert row.checkpoint["id"] == new["id"]

    async def test_recovery_with_nothing_written_is_a_clean_no_op(
        self, make_composite, clean_state
    ):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        stats = await make_composite().recover()

        assert stats["pg_checkpoints_recovered"] == 0
        assert stats["redis_delta_replayed"] == 0
        assert stats["corrupted_states"] == 0

    async def test_many_threads_are_all_reconciled(self, make_composite, clean_state):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        composite = make_composite(flush_interval=3600, flush_batch=1000)
        threads = [str(uuid.uuid4()) for _ in range(10)]
        for i, thread_id in enumerate(threads):
            cp = config_for(thread_id)
            base = make_checkpoint(i * 10)
            await composite._redis.aput(cp, base, {"i": i})
            await composite._postgres.aput(cp, base, {"i": i})
            await composite._postgres._flush()
            # Half the threads get a newer Redis write that PG has not seen.
            if i % 2 == 0:
                await composite._redis.aput(cp, make_checkpoint(i * 10 + 5), {"i": i})

        stats = await make_composite().recover()

        assert stats["redis_delta_replayed"] == 5
        assert stats["pg_checkpoints_recovered"] == 5
        assert stats["threads_skipped"] == 0


# ── Scenario 2: Redis unavailable ────────────────────────────────────────────


class TestRedisUnavailable:
    """PG snapshot alone must carry recovery (ADR-010's accepted-loss window)."""

    async def test_falls_back_to_postgres_snapshot(self, make_composite, clean_state):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        seeded = make_checkpoint(0)

        composite = make_composite(flush_interval=3600)
        await composite._redis.aput(cp, seeded, {"step": 1})
        await composite._postgres.aput(cp, seeded, {"step": 1})
        await composite._postgres._flush()

        # Simulate the Redis connection dying mid-recovery.
        composite._redis._redis_client = _DeadRedis()
        stats = await composite.recover()

        assert stats["redis_delta_replayed"] == 0
        assert stats["pg_checkpoints_recovered"] == 1
        assert stats["threads_skipped"] == 0

        # The snapshot still serves the graph.
        restored = await composite.aget(cp)
        assert restored is not None
        assert restored["id"] == seeded["id"]

    async def test_no_redis_keys_at_all_still_recovers(self, make_composite, clean_state):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        seeded = make_checkpoint(0)

        composite = make_composite(flush_interval=3600)
        await composite._postgres.aput(cp, seeded, {"step": 1})
        await composite._postgres._flush()

        stats = await composite.recover()

        assert stats["pg_checkpoints_recovered"] == 1


# ── Scenario 3: PostgreSQL unavailable ───────────────────────────────────────


class TestPostgresUnavailable:
    """A PG outage must not crash startup; threads roll over to the next pass."""

    async def test_reports_threads_as_unreconciled_without_raising(
        self, make_composite, clean_state
    ):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        composite = make_composite()
        await composite._redis.aput(cp, make_checkpoint(0), {"step": 1})

        composite._postgres = _DeadPostgres()
        stats = await composite.recover()

        assert stats["redis_delta_replayed"] == 0
        assert stats["pg_checkpoints_recovered"] == 0
        assert stats["threads_skipped"] == 1

    async def test_durable_threads_survive_a_postgres_read_failure(
        self, make_composite, clean_state
    ):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        seeded = make_checkpoint(0)

        composite = make_composite(flush_interval=3600)
        await composite._postgres.aput(cp, seeded, {"step": 1})
        await composite._postgres._flush()
        await composite._redis.aput(cp, seeded, {"step": 1})

        # Only the *read* fails; the write path is still open.
        composite._postgres = _FlakyReads(_DeadPostgres())
        stats = await composite.recover()

        assert stats["threads_skipped"] == 0
        assert stats["redis_delta_replayed"] == 1


# ── Scenario 4: both layers unavailable ──────────────────────────────────────


class TestBothLayersUnavailable:
    async def test_both_down_returns_zeroed_stats(self, make_composite, clean_state):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        composite = make_composite()
        composite._redis = _DeadRedis()
        composite._postgres = _DeadPostgres()

        stats = await composite.recover()

        assert stats == {
            "pg_checkpoints_recovered": 0,
            "redis_delta_replayed": 0,
            "conflicts_resolved": 0,
            "corrupted_states": 0,
            "threads_skipped": 0,
        }


# ── Conflict resolution ──────────────────────────────────────────────────────


class TestConflictResolution:
    async def test_divergent_state_at_the_same_instant_resolves_to_postgres(
        self, make_composite, clean_state
    ):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        ts = datetime(2026, 9, 27, 12, 0, tzinfo=UTC).isoformat()

        composite = make_composite(flush_interval=3600)
        pg_cp = {**make_checkpoint(), "ts": ts}
        redis_cp = {**make_checkpoint(), "ts": ts}

        await composite._postgres.aput(cp, pg_cp, {"winner": "pg"})
        await composite._postgres._flush()
        await composite._redis.aput(cp, redis_cp, {"winner": "redis"})

        stats = await composite.recover()

        assert stats["conflicts_resolved"] == 1

        # The durable layer won, and Redis was realigned to match it.
        assert (await composite._postgres.aget(cp))["id"] == pg_cp["id"]
        assert (await composite._redis.aget(cp))["id"] == pg_cp["id"]


# ── Timing ───────────────────────────────────────────────────────────────────


class TestRecoveryTiming:
    async def test_recovery_is_well_inside_the_startup_budget(
        self, make_composite, clean_state
    ):
        """The 30 s startup budget must not be the binding constraint in practice."""
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        import time

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        composite = make_composite(flush_interval=3600)
        await composite._postgres.aput(cp, make_checkpoint(0), {"step": 1})
        await composite._postgres._flush()
        await composite._redis.aput(cp, make_checkpoint(5), {"step": 2})

        fresh = make_composite()
        started = time.perf_counter()
        await fresh.recover(timeout_seconds=30.0)
        elapsed = time.perf_counter() - started

        assert elapsed < 10.0

    async def test_zero_timeout_still_returns_stats(self, make_composite, clean_state):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        composite = make_composite(flush_interval=3600)
        await composite._postgres.aput(cp, make_checkpoint(0), {"step": 1})
        await composite._postgres._flush()

        stats = await make_composite().recover(timeout_seconds=0.0)

        assert stats["threads_skipped"] == 1


# ── Layer discovery helpers ──────────────────────────────────────────────────


class TestThreadDiscovery:
    async def test_postgres_lists_only_threads_inside_the_window(
        self, pg_pool, clean_state
    ):
        if not await _pg_up():
            pytest.skip("PostgreSQL not available")

        recent, stale = str(uuid.uuid4()), str(uuid.uuid4())
        async with pg_pool.acquire() as conn:
            await conn.execute(AGENT_CHECKPOINTS_DDL)
            await conn.execute(
                "INSERT INTO agent_checkpoints (thread_id, checkpoint_id, state, created_at) "
                "VALUES ($1, $2, $3, NOW()), ($1, $4, $3, NOW()), ($5, $6, $3, "
                "NOW() - INTERVAL '48 hours')",
                uuid.UUID(recent), uuid.uuid4(), "{}",
                uuid.uuid4(),
                uuid.UUID(stale), uuid.uuid4(),
            )

        saver = PostgresCheckpointer(pg_pool=pg_pool)
        found = await saver.list_active_thread_ids(within_seconds=86400)

        assert found == [recent]

    async def test_redis_lists_threads_that_postgres_has_not_seen(
        self, redis_client, pg_pool, clean_state
    ):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        saver = RedisCheckpointer(redis_client=redis_client, ttl_seconds=120)
        await saver.aput(config_for(thread_id), make_checkpoint(0), {"step": 1})

        found = await saver.list_all_thread_ids()

        assert thread_id in found

    async def test_replay_lands_in_postgres_after_a_flush(
        self, make_composite, clean_state
    ):
        if not await _services_ready():
            pytest.skip("Redis and PostgreSQL required")

        thread_id = str(uuid.uuid4())
        cp = config_for(thread_id)
        replayed = make_checkpoint(3)

        composite = make_composite(flush_interval=3600)
        await composite._redis.aput(cp, replayed, {"step": 1})

        await composite.recover()
        await composite._postgres._flush()

        stored = await composite._postgres.aget(cp)
        assert stored["id"] == replayed["id"]


# ── Failure doubles ──────────────────────────────────────────────────────────


class _DeadRedis:
    """Stands in for a Redis client whose connection is gone."""

    async def aget_tuple(self, config):
        raise ConnectionError("redis down")

    async def list_all_thread_ids(self):
        raise ConnectionError("redis down")

    async def aget(self, config):
        raise ConnectionError("redis down")

    async def aput(self, config, checkpoint, metadata, new_versions=None):
        raise ConnectionError("redis down")


class _DeadPostgres:
    """Stands in for a PostgreSQL layer that is refusing connections."""

    async def aget_tuple(self, config):
        raise ConnectionError("postgres down")

    async def list_active_thread_ids(self, within_seconds=86400):
        raise ConnectionError("postgres down")

    async def aget(self, config):
        raise ConnectionError("postgres down")

    async def aput(self, config, checkpoint, metadata, new_versions=None):
        raise ConnectionError("postgres down")

    async def replay_checkpoint(self, thread_id, checkpoint, metadata=None):
        raise ConnectionError("postgres down")


class _FlakyReads:
    """Wraps a dead layer so only its read paths fail, leaving writes open."""

    def __init__(self, inner: _DeadPostgres) -> None:
        self._inner = inner

    async def aget_tuple(self, config):
        raise ConnectionError("postgres down")

    async def list_active_thread_ids(self, within_seconds=86400):
        raise ConnectionError("postgres down")

    async def aget(self, config):
        raise ConnectionError("postgres down")

    async def replay_checkpoint(self, thread_id, checkpoint, metadata=None):
        # Write path intact: this is a read-side outage.
        return None
