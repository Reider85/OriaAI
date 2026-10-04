"""Integration tests for PostgresCheckpointer against a real PostgreSQL (ADR-010).

Requires the ``agent_checkpoints`` table from ADR-001. The fixture creates it if
missing so the suite is runnable standalone; it deliberately matches
``ARCHITECT.md`` §6 exactly and is not a schema change owned by B-2.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from langgraph.checkpoint.base import Checkpoint, RunnableConfig

from llm_client.orchestration.checkpointers.postgres_checkpointer import (
    PostgresCheckpointer,
)

pytestmark = [pytest.mark.integration]

# ARCHITECT.md §6 — PRIMARY KEY (thread_id, checkpoint_id) drives the ON CONFLICT upsert.
AGENT_CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    thread_id UUID NOT NULL,
    checkpoint_id UUID NOT NULL,
    parent_id UUID,
    state JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP(timezone=True) NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_id)
)
"""


def _dsn() -> str:
    """Build an asyncpg DSN from DATABASE_URL (which uses the SQLAlchemy scheme)."""
    url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5434/llm_client"
    )
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def make_checkpoint(index: int) -> Checkpoint:
    return Checkpoint(
        v=1,
        id=str(uuid.uuid4()),
        ts=f"2026-09-27T10:00:{index:02d}+00:00",
        channel_values={"messages": [{"role": "user", "content": f"integration-{index}"}]},
        channel_versions={"messages": str(index + 1)},
        versions_seen={"messages": {str(index + 1): str(index + 1)}},
        updated_channels=["messages"],
    )


@pytest.fixture
async def pg_pool():
    pool = None
    try:
        pool = await asyncpg.create_pool(dsn=_dsn(), min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(AGENT_CHECKPOINTS_DDL)
    except Exception as exc:  # noqa: BLE001 — any failure means PG is unusable here
        if pool is not None:
            await pool.close()
        pytest.skip(f"PostgreSQL not available: {exc}")
    yield pool
    await pool.close()


@pytest.fixture
async def thread_id(pg_pool) -> AsyncIterator[str]:
    """A fresh thread per test, with its rows removed afterwards."""
    value = str(uuid.uuid4())
    yield value
    await pg_pool.execute("DELETE FROM agent_checkpoints WHERE thread_id = $1::uuid", value)


@pytest.fixture
def config(thread_id) -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": thread_id})


@pytest.fixture
def checkpointer(pg_pool) -> PostgresCheckpointer:
    # Flusher intentionally not started (B-4 owns that); tests call _flush().
    return PostgresCheckpointer(pg_pool=pg_pool)


class RecordingPool:
    """Delegates to a real pool while recording ``execute`` calls.

    ``asyncpg.Pool`` attributes are read-only, so the methods are wrapped rather
    than monkeypatched onto the instance.
    """

    def __init__(self, pool, fail: bool = False) -> None:
        self._pool = pool
        self.fail = fail
        self.execute_calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name):
        return getattr(self._pool, name)

    async def execute(self, sql: str, *args):
        self.execute_calls.append((sql, args))
        if self.fail:
            raise ConnectionRefusedError("postgres is down")
        return await self._pool.execute(sql, *args)


async def _count_rows(pool, thread_id: str) -> int:
    return await pool.fetchval(
        "SELECT count(*) FROM agent_checkpoints WHERE thread_id = $1::uuid", thread_id
    )


class TestRoundTrip:
    async def test_put_flush_get(self, checkpointer, pg_pool, config, thread_id):
        """put → flush → get: the ADR-010 write path end to end."""
        checkpoint = make_checkpoint(0)
        await checkpointer.adelete_thread(thread_id)

        await checkpointer.aput(config, checkpoint, {"source": "loop"})
        assert await _count_rows(pg_pool, thread_id) == 0, "aput must not write synchronously"

        await checkpointer._flush()
        assert await _count_rows(pg_pool, thread_id) == 1

        # New instance: reads come from PG, not the (now empty) buffer.
        reader = PostgresCheckpointer(pg_pool=pg_pool)
        retrieved = await reader.aget(config)

        assert retrieved is not None
        assert retrieved["id"] == checkpoint["id"]
        assert retrieved["channel_values"] == checkpoint["channel_values"]

    async def test_buffer_is_readable_before_flush(self, checkpointer, config, thread_id):
        await checkpointer.adelete_thread(thread_id)
        checkpoint = make_checkpoint(0)

        await checkpointer.aput(config, checkpoint, {})
        retrieved = await checkpointer.aget(config)

        assert retrieved is not None
        assert retrieved["id"] == checkpoint["id"]

    async def test_batched_upsert_of_50_rows(self, checkpointer, pg_pool, config, thread_id):
        """DoD: 50 checkpoints land via a single batched INSERT."""
        await checkpointer.adelete_thread(thread_id)
        for i in range(50):
            await checkpointer.aput(config, make_checkpoint(i), {"step": i})

        await checkpointer._flush()

        assert await _count_rows(pg_pool, thread_id) == 50
        assert checkpointer.buffer_size == 0

    async def test_upsert_is_idempotent(self, checkpointer, pg_pool, config, thread_id):
        """A retried flush must not create duplicate rows (ON CONFLICT)."""
        await checkpointer.adelete_thread(thread_id)
        checkpoint = make_checkpoint(0)

        for _ in range(3):
            await checkpointer.aput(config, checkpoint, {"attempt": True})
            await checkpointer._flush()

        assert await _count_rows(pg_pool, thread_id) == 1

    async def test_delete_thread_removes_rows(self, checkpointer, pg_pool, config, thread_id):
        await checkpointer.adelete_thread(thread_id)
        await checkpointer.aput(config, make_checkpoint(0), {})
        await checkpointer._flush()
        assert await _count_rows(pg_pool, thread_id) == 1

        await checkpointer.adelete_thread(thread_id)

        assert await _count_rows(pg_pool, thread_id) == 0
        assert await checkpointer.aget(config) is None


class TestListing:
    async def test_alist_returns_flushed_checkpoints(self, checkpointer, config, thread_id):
        await checkpointer.adelete_thread(thread_id)
        for i in range(5):
            await checkpointer.aput(config, make_checkpoint(i), {"step": i})
        await checkpointer._flush()

        results = [t async for t in checkpointer.alist(config)]

        assert len(results) == 5
        assert all(t.metadata == {"step": i} for i, t in enumerate(reversed(results)))

    async def test_alist_respects_limit(self, checkpointer, config, thread_id):
        await checkpointer.adelete_thread(thread_id)
        for i in range(5):
            await checkpointer.aput(config, make_checkpoint(i), {})
        await checkpointer._flush()

        results = [t async for t in checkpointer.alist(config, limit=3)]

        assert len(results) == 3

    async def test_alist_filters_on_metadata(self, checkpointer, config, thread_id):
        await checkpointer.adelete_thread(thread_id)
        for i in range(4):
            source = "loop" if i % 2 == 0 else "input"
            await checkpointer.aput(config, make_checkpoint(i), {"source": source})
        await checkpointer._flush()

        results = [t async for t in checkpointer.alist(config, filter={"source": "input"})]

        assert len(results) == 2
        assert all(t.metadata["source"] == "input" for t in results)

    async def test_threads_are_isolated(self, checkpointer, config, thread_id):
        other_thread = str(uuid.uuid4())
        other_config = RunnableConfig(configurable={"thread_id": other_thread})
        await checkpointer.adelete_thread(thread_id)
        await checkpointer.adelete_thread(other_thread)

        await checkpointer.aput(config, make_checkpoint(0), {})
        await checkpointer.aput(other_config, make_checkpoint(1), {})
        await checkpointer._flush()

        mine = [t async for t in checkpointer.alist(config)]
        theirs = [t async for t in checkpointer.alist(other_config)]

        assert len(mine) == 1
        assert len(theirs) == 1
        assert mine[0].checkpoint["id"] != theirs[0].checkpoint["id"]


class TestSerialization:
    async def test_non_json_channel_values_round_trip(self, checkpointer, config, thread_id):
        """AIMessage is not JSON-serializable; the serde envelope must survive PG JSONB."""
        from langchain_core.messages import AIMessage

        await checkpointer.adelete_thread(thread_id)
        checkpoint = make_checkpoint(0) | {
            "channel_values": {"messages": [AIMessage(content="structured answer")]}
        }

        await checkpointer.aput(config, checkpoint, {})
        await checkpointer._flush()

        reader = PostgresCheckpointer(pg_pool=checkpointer._pg_pool)
        retrieved = await reader.aget(config)

        assert retrieved["channel_values"]["messages"][0].content == "structured answer"

    async def test_parent_id_persists(self, checkpointer, config, thread_id):
        await checkpointer.adelete_thread(thread_id)
        parent = make_checkpoint(0)
        child = make_checkpoint(1) | {"parent_checkpoint_id": parent["id"]}

        await checkpointer.aput(config, child, {})
        await checkpointer._flush()

        result = await checkpointer.aget_tuple(config)

        assert result.parent_config["configurable"]["checkpoint_id"] == parent["id"]

    async def test_state_stored_as_jsonb(self, checkpointer, pg_pool, config, thread_id):
        """state must be valid JSONB in the DB, not a byte blob."""
        await checkpointer.adelete_thread(thread_id)
        await checkpointer.aput(config, make_checkpoint(0), {})
        await checkpointer._flush()

        state_type = await pg_pool.fetchval(
            """
            SELECT pg_typeof(state)::text FROM agent_checkpoints
            WHERE thread_id = $1::uuid LIMIT 1
            """,
            thread_id,
        )

        assert state_type == "jsonb"


class TestLatency:
    async def test_aput_stays_under_1ms(self, checkpointer, config, thread_id):
        """DoD: aput is a buffer append, not a PG round-trip."""
        await checkpointer.adelete_thread(thread_id)
        loop = asyncio.get_running_loop()

        checkpoints = [make_checkpoint(i) for i in range(50)]
        start = loop.time()
        for checkpoint in checkpoints:
            await checkpointer.aput(config, checkpoint, {})
        elapsed_ms = (loop.time() - start) * 1000 / len(checkpoints)

        assert elapsed_ms < 1.0, f"aput averaged {elapsed_ms:.3f} ms"
        await checkpointer._flush()

    async def test_flush_of_50_rows_under_200ms(self, checkpointer, pg_pool, config, thread_id):
        """DoD: 50 checkpoints upsert in under 200 ms."""
        await checkpointer.adelete_thread(thread_id)
        checkpointer.flush_batch_size = 50
        for i in range(50):
            await checkpointer.aput(config, make_checkpoint(i), {})

        loop = asyncio.get_running_loop()
        start = loop.time()
        await checkpointer._flush()
        elapsed_ms = (loop.time() - start) * 1000

        assert await _count_rows(pg_pool, thread_id) == 50
        assert elapsed_ms < 200.0, f"flush took {elapsed_ms:.1f} ms"

    async def test_batching_reduces_pg_round_trips(self, pg_pool, config, thread_id):
        """ADR-010: 50 buffered checkpoints must cost one INSERT, not 50."""
        recorder = RecordingPool(pg_pool)
        checkpointer = PostgresCheckpointer(pg_pool=recorder, flush_batch_size=50)
        await checkpointer.adelete_thread(thread_id)

        for i in range(50):
            await checkpointer.aput(config, make_checkpoint(i), {})
        recorder.execute_calls.clear()  # ignore the setup DELETE

        await checkpointer._flush()

        assert len(recorder.execute_calls) == 1
        assert recorder.execute_calls[0][0].lstrip().startswith("INSERT")
        assert len(recorder.execute_calls[0][1]) == 300  # 50 rows x 6 columns


class TestFlushLoop:
    async def test_flush_loop_drains_periodically(self, pg_pool, config, thread_id):
        checkpointer = PostgresCheckpointer(pg_pool=pg_pool, flush_interval_seconds=1)
        await checkpointer.adelete_thread(thread_id)
        await checkpointer.aput(config, make_checkpoint(0), {})

        task = asyncio.create_task(checkpointer._flush_loop())
        try:
            for _ in range(40):
                await asyncio.sleep(0.1)
                if checkpointer.buffer_size == 0:
                    break
        finally:
            checkpointer._stopping = True
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert await _count_rows(pg_pool, thread_id) == 1

    async def test_stopping_flag_ends_the_loop(self, pg_pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pg_pool, flush_interval_seconds=5)
        checkpointer._stopping = True

        # Returns immediately rather than sleeping out the interval.
        await asyncio.wait_for(checkpointer._flush_loop(), timeout=2.0)


class TestFailureHandling:
    async def test_flush_error_preserves_buffer(self, pg_pool, config, thread_id):
        # Clean up while PG is still healthy, then point the saver at a pool that fails.
        await PostgresCheckpointer(pg_pool=pg_pool).adelete_thread(thread_id)

        failing = RecordingPool(pg_pool, fail=True)
        checkpointer = PostgresCheckpointer(pg_pool=failing)
        await checkpointer.aput(config, make_checkpoint(0), {})

        from llm_client.orchestration.checkpointers.errors import CheckpointWriteError

        with pytest.raises(CheckpointWriteError):
            await checkpointer._flush()

        assert checkpointer.buffer_size == 1, "pending checkpoint must survive for retry"

        # PG recovers: the retry drains the buffer and the row lands.
        healthy = PostgresCheckpointer(pg_pool=pg_pool)
        checkpointer._pg_pool = healthy._pg_pool
        await checkpointer._flush()
        assert checkpointer.buffer_size == 0
        assert await _count_rows(pg_pool, thread_id) == 1
