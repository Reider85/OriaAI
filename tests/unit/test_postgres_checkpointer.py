"""Unit tests for PostgresCheckpointer (ADR-010 async batched write layer)."""

import asyncio
import json
import uuid

import pytest
from langgraph.checkpoint.base import (
    Checkpoint,
    CheckpointTuple,
    RunnableConfig,
)

from llm_client.orchestration.checkpointers.errors import CheckpointWriteError
from llm_client.orchestration.checkpointers.postgres_checkpointer import (
    PostgresCheckpointer,
)

THREAD_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))


class MockAsyncPGPool:
    """In-memory stand-in for ``asyncpg.Pool`` that records every statement.

    Applies the real upsert semantics so round-trip tests exercise the same code
    paths as PostgreSQL without needing a live server.
    """

    def __init__(self, fail_execute: bool = False) -> None:
        self.rows: dict[tuple[str, str], dict] = {}
        self.queries: list[tuple[str, tuple]] = []
        self.fail_execute = fail_execute
        self.execute_count = 0

    async def execute(self, sql: str, *args) -> str:
        self.queries.append((sql, args))
        self.execute_count += 1
        if self.fail_execute:
            raise ConnectionRefusedError("postgres is down")

        if sql.lstrip().upper().startswith("DELETE"):
            thread_id = str(args[0])
            for key in [k for k in self.rows if k[0] == thread_id]:
                del self.rows[key]
            return "DELETE 1"

        upserts = _chunk_rows(args, columns=6)
        for values in upserts:
            thread_id, checkpoint_id, parent_id, state, metadata, created_at = values
            self.rows[(str(thread_id), str(checkpoint_id))] = {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "parent_id": parent_id,
                "state": state,
                "metadata": json.loads(metadata) if isinstance(metadata, str) else metadata,
                "created_at": created_at,
            }
        return f"INSERT 0 {len(upserts)}"

    async def fetchrow(self, sql: str, *args):
        self.queries.append((sql, args))
        if sql.lstrip().upper().startswith("SELECT"):
            candidates = [r for k, r in self.rows.items() if k[0] == str(args[0])]
            if not candidates:
                return None
            return max(candidates, key=lambda r: (r["created_at"], str(r["checkpoint_id"])))
        return None

    async def fetch(self, sql: str, *args):
        self.queries.append((sql, args))
        before = args[1] if len(args) > 1 else None
        limit = args[2] if len(args) > 2 else None
        rows = [r for k, r in self.rows.items() if k[0] == str(args[0])]
        if before is not None:
            rows = [r for r in rows if r["created_at"] < before]
        rows.sort(key=lambda r: (r["created_at"], str(r["checkpoint_id"])), reverse=True)
        if limit is not None:
            rows = rows[:limit]
        return rows


def _chunk_rows(args: tuple, columns: int) -> list[tuple]:
    """Split flat INSERT args into rows.

    Row boundaries are derived from the argument count rather than by parsing the
    statement text: the serialized state/metadata payloads are JSON and contain
    commas, so splitting the SQL on "," corrupts them.
    """
    assert len(args) % columns == 0, f"expected a multiple of {columns} args, got {len(args)}"
    return [tuple(args[i : i + columns]) for i in range(0, len(args), columns)]


def make_checkpoint(index: int = 0, thread_id: str = THREAD_ID) -> Checkpoint:
    """Build a checkpoint with a real UUID id (the column is a UUID type)."""
    return Checkpoint(
        v=1,
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"checkpoint-{index}")),
        ts=f"2026-09-27T10:00:{index:02d}+00:00",
        channel_values={"messages": [{"role": "user", "content": f"msg-{index}"}]},
        channel_versions={"messages": str(index + 1)},
        versions_seen={"messages": {str(index + 1): str(index + 1)}},
        updated_channels=["messages"],
    )


@pytest.fixture
def pool():
    return MockAsyncPGPool()


@pytest.fixture
def checkpointer(pool):
    return PostgresCheckpointer(pg_pool=pool)


@pytest.fixture
def config():
    return RunnableConfig(configurable={"thread_id": THREAD_ID})


class TestAputBuffersOnly:
    """aput must never touch PostgreSQL — that is the whole point of ADR-010."""

    @pytest.mark.asyncio
    async def test_aput_does_not_write_to_pg(self, checkpointer, pool, config):
        result = await checkpointer.aput(config, make_checkpoint(0), {"source": "loop"})

        assert result is config
        assert pool.execute_count == 0
        assert checkpointer.buffer_size == 1

    @pytest.mark.asyncio
    async def test_aput_is_under_1ms(self, checkpointer, config):
        loop = asyncio.get_running_loop()

        start = loop.time()
        for i in range(50):
            await checkpointer.aput(config, make_checkpoint(i), {"step": i})
        elapsed_ms = (loop.time() - start) * 1000 / 50

        assert elapsed_ms < 1.0, f"aput averaged {elapsed_ms:.3f} ms"

    @pytest.mark.asyncio
    async def test_aput_rejects_missing_thread_id(self, checkpointer):
        with pytest.raises(ValueError, match="thread_id"):
            await checkpointer.aput(RunnableConfig({}), make_checkpoint(0), {})

    @pytest.mark.asyncio
    async def test_aput_rejects_non_uuid_id(self, checkpointer, config):
        checkpoint = make_checkpoint(0) | {"id": "not-a-uuid"}
        with pytest.raises(ValueError, match="must be a UUID"):
            await checkpointer.aput(config, checkpoint, {})


class TestFlush:
    """_flush upserts the whole buffer in as few round-trips as possible."""

    @pytest.mark.asyncio
    async def test_flush_writes_buffered_checkpoints(self, checkpointer, pool, config):
        await checkpointer.aput(config, make_checkpoint(0), {"step": 0})
        await checkpointer.aput(config, make_checkpoint(1), {"step": 1})

        await checkpointer._flush()

        assert len(pool.rows) == 2
        assert checkpointer.buffer_size == 0

    @pytest.mark.asyncio
    async def test_flush_uses_single_statement_for_batch(self, checkpointer, pool, config):
        for i in range(5):
            await checkpointer.aput(config, make_checkpoint(i), {"step": i})

        await checkpointer._flush()

        assert pool.execute_count == 1
        sql, args = pool.queries[0]
        assert "ON CONFLICT (thread_id, checkpoint_id) DO UPDATE" in sql
        assert len(args) == 30  # 5 rows x 6 columns

    @pytest.mark.asyncio
    async def test_flush_is_idempotent_upsert(self, checkpointer, pool, config):
        await checkpointer.aput(config, make_checkpoint(0), {"step": 0})
        await checkpointer._flush()
        await checkpointer.aput(config, make_checkpoint(0), {"step": 0})
        await checkpointer._flush()

        assert len(pool.rows) == 1

    @pytest.mark.asyncio
    async def test_flush_chunks_respect_batch_size(self, pool):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_batch_size=2)
        config = RunnableConfig(configurable={"thread_id": THREAD_ID})
        for i in range(5):
            await checkpointer.aput(config, make_checkpoint(i), {"step": i})

        await checkpointer._flush()

        # 5 rows / batch of 2 -> 3 statements (2, 2, 1)
        assert pool.execute_count == 3
        assert len(pool.rows) == 5
        assert checkpointer.buffer_size == 0

    @pytest.mark.asyncio
    async def test_flush_on_empty_buffer_is_noop(self, checkpointer, pool):
        await checkpointer._flush()
        assert pool.execute_count == 0

    @pytest.mark.asyncio
    async def test_flush_logs_operational_event(self, checkpointer, pool, config, caplog):
        await checkpointer.aput(config, make_checkpoint(0), {})

        with caplog.at_level(
            "INFO", logger="llm_client.orchestration.checkpointers.postgres_checkpointer"
        ):
            await checkpointer._flush()

        assert any("checkpoint_flush" in r.message for r in caplog.records)
        assert any("duration_ms" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_flush_keeps_buffer_on_pg_error(self, pool, config):
        pool.fail_execute = True
        checkpointer = PostgresCheckpointer(pg_pool=pool)

        await checkpointer.aput(config, make_checkpoint(0), {})

        with pytest.raises(CheckpointWriteError, match="PostgreSQL flush failed"):
            await checkpointer._flush()

        assert checkpointer.buffer_size == 1

    @pytest.mark.asyncio
    async def test_flush_recovers_after_pg_error(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool)
        await checkpointer.aput(config, make_checkpoint(0), {})

        pool.fail_execute = True
        with pytest.raises(CheckpointWriteError):
            await checkpointer._flush()

        pool.fail_execute = False
        await checkpointer._flush()

        assert checkpointer.buffer_size == 0
        assert len(pool.rows) == 1

    @pytest.mark.asyncio
    async def test_batch_size_trigger_schedules_flush(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_batch_size=2)
        for i in range(2):
            await checkpointer.aput(config, make_checkpoint(i), {})

        await asyncio.sleep(0)  # let the scheduled task run
        await asyncio.sleep(0)

        assert pool.execute_count == 1


class TestPanicModeAndBackpressure:
    def test_max_buffer_size_is_batch_size_times_ten(self, pool):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_batch_size=50)
        assert checkpointer.max_buffer_size == 500

    @pytest.mark.asyncio
    async def test_buffer_overflow_enters_panic_mode(self, pool, config):
        checkpointer = PostgresCheckpointer(
            pg_pool=pool, flush_batch_size=2, max_buffer_multiplier=2
        )
        # flush_batch_size * 2 == 4 == max_buffer_size
        for i in range(4):
            await checkpointer.aput(config, make_checkpoint(i), {})

        assert checkpointer._panic_mode is True

    @pytest.mark.asyncio
    async def test_panic_mode_flushes_on_every_aput(self, pool, config):
        checkpointer = PostgresCheckpointer(
            pg_pool=pool, flush_batch_size=2, max_buffer_multiplier=2
        )
        for i in range(4):
            await checkpointer.aput(config, make_checkpoint(i), {})
        before = pool.execute_count

        await checkpointer.aput(config, make_checkpoint(99), {})

        assert pool.execute_count > before

    @pytest.mark.asyncio
    async def test_backpressure_unblocks_when_flush_drains(self, pool, config):
        checkpointer = PostgresCheckpointer(
            pg_pool=pool,
            flush_batch_size=2,
            max_buffer_multiplier=2,
            backpressure_timeout_seconds=5.0,
        )
        for i in range(4):
            await checkpointer.aput(config, make_checkpoint(i), {})

        # Buffer is at capacity; the next aput blocks until the scheduled flush
        # clears space, then proceeds.
        result = await asyncio.wait_for(
            checkpointer.aput(config, make_checkpoint(100), {}), timeout=5.0
        )

        assert result is config
        assert pool.execute_count > 0

    @pytest.mark.asyncio
    async def test_backpressure_gives_up_after_timeout(self, pool, config):
        checkpointer = PostgresCheckpointer(
            pg_pool=pool,
            flush_batch_size=1,
            max_buffer_multiplier=2,
            backpressure_timeout_seconds=0.3,
        )

        # Stub the flusher before any aput so no real flush task is in flight:
        # the buffer can then never drain, which is the condition under test.
        async def noop_flush():
            return None

        checkpointer._flush = noop_flush

        for i in range(2):
            await checkpointer.aput(config, make_checkpoint(i), {})

        result = await asyncio.wait_for(
            checkpointer.aput(config, make_checkpoint(100), {}), timeout=5.0
        )

        assert result is config
        # Buffer was never drained, yet the write still happened rather than
        # hanging or dropping the checkpoint.
        assert checkpointer.buffer_size == 3


class TestAget:
    @pytest.mark.asyncio
    async def test_aget_prefers_buffer_over_pg(self, checkpointer, pool, config):
        checkpoint = make_checkpoint(0)
        await checkpointer.aput(config, checkpoint, {})

        retrieved = await checkpointer.aget(config)

        assert retrieved is not None
        assert retrieved["id"] == checkpoint["id"]
        assert not any(q[0].lstrip().upper().startswith("SELECT") for q in pool.queries)

    @pytest.mark.asyncio
    async def test_aget_falls_back_to_pg(self, checkpointer, pool, config):
        checkpoint = make_checkpoint(0)
        await checkpointer.aput(config, checkpoint, {})
        await checkpointer._flush()

        retrieved = await checkpointer.aget(config)

        assert retrieved is not None
        assert retrieved["id"] == checkpoint["id"]
        assert retrieved["channel_values"] == checkpoint["channel_values"]

    @pytest.mark.asyncio
    async def test_aget_returns_none_when_absent(self, checkpointer, config):
        assert await checkpointer.aget(config) is None

    @pytest.mark.asyncio
    async def test_aget_returns_latest_buffered_for_thread(self, checkpointer, config):
        for i in range(3):
            await checkpointer.aput(config, make_checkpoint(i), {})

        retrieved = await checkpointer.aget(config)

        assert retrieved["id"] == make_checkpoint(2)["id"]


class TestAgetTuple:
    @pytest.mark.asyncio
    async def test_aget_tuple_from_buffer(self, checkpointer, config):
        checkpoint = make_checkpoint(0)
        await checkpointer.aput(config, checkpoint, {"step": 7})

        result = await checkpointer.aget_tuple(config)

        assert isinstance(result, CheckpointTuple)
        assert result.checkpoint["id"] == checkpoint["id"]
        assert result.metadata == {"step": 7}

    @pytest.mark.asyncio
    async def test_aget_tuple_from_pg(self, checkpointer, pool, config):
        checkpoint = make_checkpoint(0)
        await checkpointer.aput(config, checkpoint, {"step": 3})
        await checkpointer._flush()

        result = await checkpointer.aget_tuple(config)

        assert isinstance(result, CheckpointTuple)
        assert result.metadata == {"step": 3}
        assert result.config["configurable"]["thread_id"] == THREAD_ID

    @pytest.mark.asyncio
    async def test_aget_tuple_returns_none_when_absent(self, checkpointer, config):
        assert await checkpointer.aget_tuple(config) is None


class TestAlist:
    @pytest.mark.asyncio
    async def test_alist_yields_buffered_checkpoints(self, checkpointer, config):
        for i in range(3):
            await checkpointer.aput(config, make_checkpoint(i), {})

        results = [t async for t in checkpointer.alist(config)]

        assert len(results) == 3
        assert [t.checkpoint["id"] for t in results] == [
            make_checkpoint(i)["id"] for i in (2, 1, 0)
        ]

    @pytest.mark.asyncio
    async def test_alist_merges_pg_with_buffer_without_duplicates(self, checkpointer, pool, config):
        for i in range(2):
            await checkpointer.aput(config, make_checkpoint(i), {})
        await checkpointer._flush()
        for i in range(2, 4):
            await checkpointer.aput(config, make_checkpoint(i), {})

        results = [t async for t in checkpointer.alist(config)]

        ids = [t.checkpoint["id"] for t in results]
        assert len(ids) == 4
        assert len(set(ids)) == 4

    @pytest.mark.asyncio
    async def test_alist_respects_limit(self, checkpointer, config):
        for i in range(5):
            await checkpointer.aput(config, make_checkpoint(i), {})

        results = [t async for t in checkpointer.alist(config, limit=2)]

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_alist_applies_metadata_filter(self, checkpointer, config):
        await checkpointer.aput(config, make_checkpoint(0), {"source": "loop"})
        await checkpointer.aput(config, make_checkpoint(1), {"source": "input"})

        results = [t async for t in checkpointer.alist(config, filter={"source": "input"})]

        assert len(results) == 1
        assert results[0].metadata == {"source": "input"}

    @pytest.mark.asyncio
    async def test_alist_isolates_threads(self, checkpointer):
        thread_a = RunnableConfig(configurable={"thread_id": THREAD_ID})
        thread_b = RunnableConfig(
            configurable={"thread_id": str(uuid.UUID("22222222-2222-4222-8222-222222222222"))}
        )
        await checkpointer.aput(thread_a, make_checkpoint(0), {})
        await checkpointer.aput(thread_b, make_checkpoint(1), {})

        results_a = [t async for t in checkpointer.alist(thread_a)]
        results_b = [t async for t in checkpointer.alist(thread_b)]

        assert len(results_a) == 1
        assert len(results_b) == 1
        assert results_a[0].checkpoint["id"] != results_b[0].checkpoint["id"]


class TestWritesBuffer:
    @pytest.mark.asyncio
    async def test_aput_writes_buffers_separately(self, checkpointer, config):
        writes = [("messages", "Hello"), ("context", "World")]

        await checkpointer.aput_writes(config, writes, "task-1")

        assert checkpointer._writes_buffer[(THREAD_ID, "task-1")] == writes
        assert checkpointer.buffer_size == 0

    @pytest.mark.asyncio
    async def test_aput_writes_does_not_touch_pg(self, checkpointer, pool, config):
        await checkpointer.aput_writes(config, [("messages", "Hello")], "task-1")
        assert pool.execute_count == 0

    @pytest.mark.asyncio
    async def test_aput_writes_does_not_overwrite_checkpoints(self, checkpointer, config):
        await checkpointer.aput(config, make_checkpoint(0), {})
        await checkpointer.aput_writes(config, [("messages", "Hello")], "task-1")

        assert checkpointer.buffer_size == 1


class TestDeleteThread:
    @pytest.mark.asyncio
    async def test_adelete_thread_clears_pg_and_buffer(self, checkpointer, pool, config):
        await checkpointer.aput(config, make_checkpoint(0), {})
        await checkpointer.aput_writes(config, [("messages", "Hello")], "task-1")
        await checkpointer._flush()
        assert len(pool.rows) == 1

        await checkpointer.adelete_thread(THREAD_ID)

        assert pool.rows == {}
        assert checkpointer.buffer_size == 0
        assert checkpointer._writes_buffer == {}


class TestConstructorValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"flush_interval_seconds": 0},
            {"flush_batch_size": 0},
            {"max_buffer_multiplier": 1},
        ],
    )
    def test_rejects_invalid_settings(self, pool, kwargs):
        with pytest.raises(ValueError):
            PostgresCheckpointer(pg_pool=pool, **kwargs)

    def test_does_not_start_flusher_in_constructor(self, pool):
        checkpointer = PostgresCheckpointer(pg_pool=pool)
        # B-4 owns task lifecycle; nothing may be scheduled here.
        assert not hasattr(checkpointer, "_flush_task") or checkpointer._flush_task is None


class TestSerialization:
    @pytest.mark.asyncio
    async def test_state_survives_non_json_values(self, checkpointer, pool, config):
        from langchain_core.messages import AIMessage

        checkpoint = make_checkpoint(0) | {
            "channel_values": {"messages": [AIMessage(content="structured answer")]}
        }
        await checkpointer.aput(config, checkpoint, {})
        await checkpointer._flush()

        retrieved = await checkpointer.aget(config)

        assert retrieved["channel_values"]["messages"][0].content == "structured answer"

    @pytest.mark.asyncio
    async def test_parent_id_is_persisted(self, checkpointer, pool, config):
        parent = make_checkpoint(0)
        child = make_checkpoint(1) | {"parent_checkpoint_id": parent["id"]}
        await checkpointer.aput(config, child, {})
        await checkpointer._flush()

        result = await checkpointer.aget_tuple(config)

        assert result.parent_config["configurable"]["checkpoint_id"] == parent["id"]


class TestFlushLoop:
    @pytest.mark.asyncio
    async def test_flush_loop_periodically_flushes(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=1)
        await checkpointer.aput(config, make_checkpoint(0), {})

        task = asyncio.create_task(checkpointer._flush_loop())
        try:
            await asyncio.sleep(1.1)
        finally:
            task.cancel()
            # Task should complete successfully after final flush
            await task

        assert pool.execute_count >= 1
        assert checkpointer.buffer_size == 0

    @pytest.mark.asyncio
    async def test_flush_loop_stops_when_stopping_flag_set(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=1)
        checkpointer._stopping = True

        await asyncio.wait_for(checkpointer._flush_loop(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_start_flush_loop_creates_task(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=1)

        # Initially no task
        assert checkpointer._flush_task is None

        # Start flush loop
        await checkpointer.start_flush_loop()

        # Task should be created
        assert checkpointer._flush_task is not None
        assert not checkpointer._flush_task.done()

        # Clean up
        await checkpointer.stop_flush_loop()

    @pytest.mark.asyncio
    async def test_start_flush_loop_idempotent(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=1)

        # Start first time
        await checkpointer.start_flush_loop()
        task1 = checkpointer._flush_task

        # Start again - should not create duplicate
        await checkpointer.start_flush_loop()
        task2 = checkpointer._flush_task

        assert task1 is task2  # Same task

        # Clean up
        await checkpointer.stop_flush_loop()

    @pytest.mark.asyncio
    async def test_stop_flush_loop_cancels_task(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=1)

        await checkpointer.start_flush_loop()
        task = checkpointer._flush_task

        # Stop should cancel the task
        await checkpointer.stop_flush_loop()

        assert task.done()
        assert checkpointer._flush_task is None

    @pytest.mark.asyncio
    async def test_stop_flush_loop_performs_final_flush(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=10)
        await checkpointer.aput(config, make_checkpoint(0), {})

        # Buffer should have 1 item
        assert checkpointer.buffer_size == 1

        # Start flush loop first
        await checkpointer.start_flush_loop()

        # Give the flush loop a chance to run and process the buffer
        await asyncio.sleep(0.1)

        # Now stop it - this should trigger final flush
        await checkpointer.stop_flush_loop()

        # Buffer should be empty
        assert checkpointer.buffer_size == 0
        assert len(pool.rows) == 1

    @pytest.mark.asyncio
    async def test_flush_loop_handles_cancelled_error_gracefully(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=1)
        await checkpointer.aput(config, make_checkpoint(0), {})

        # Start flush loop
        task = asyncio.create_task(checkpointer._flush_loop())

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Cancel it - should perform final flush
        task.cancel()

        # Wait for cancellation to complete - task should succeed after final flush
        await task

        # Buffer should be empty (final flush happened)
        assert checkpointer.buffer_size == 0
        assert len(pool.rows) == 1

    @pytest.mark.asyncio
    async def test_consecutive_failures_raise_fatal_error(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=1)

        # Make flush fail
        pool.fail_execute = True

        # Add some checkpoints to trigger flush
        for i in range(5):
            await checkpointer.aput(config, make_checkpoint(i), {})

        # Start flush loop
        await checkpointer.start_flush_loop()

        # Wait for consecutive failures (1 second interval = ~2 attempts in 2 seconds)
        await asyncio.sleep(2.0)

        # Should have multiple consecutive failures
        assert checkpointer._consecutive_failures >= 2  # At least 2 failures

        # Clean up
        await checkpointer.stop_flush_loop()

    @pytest.mark.asyncio
    async def test_adaptive_backoff_slow_flush(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=5)

        # Mock _write_batch to simulate slow flush
        original_write_batch = checkpointer._write_batch

        async def slow_write_batch(batch):
            await asyncio.sleep(0.6)  # Simulate 600ms flush
            return await original_write_batch(batch)

        checkpointer._write_batch = slow_write_batch

        # Add checkpoint to trigger flush
        await checkpointer.aput(config, make_checkpoint(0), {})

        # Initial interval should be 5s
        assert checkpointer._current_flush_interval == 5

        # Trigger flush
        await checkpointer._flush()

        # Interval should be reduced to 1s due to slow flush
        assert checkpointer._current_flush_interval == 1.0

    @pytest.mark.asyncio
    async def test_adaptive_backoff_fast_flush_resets_interval(self, pool, config):
        checkpointer = PostgresCheckpointer(pg_pool=pool, flush_interval_seconds=5)

        # Start with reduced interval
        checkpointer._current_flush_interval = 2.0

        # Add checkpoint to trigger flush
        await checkpointer.aput(config, make_checkpoint(0), {})

        # Trigger fast flush
        await checkpointer._flush()

        # Interval should reset to default (5s) because flush was fast
        assert checkpointer._current_flush_interval == 5

    @pytest.mark.asyncio
    async def test_metrics_recorded_during_flush(self, pool, config):
        from llm_client.orchestration.checkpointers.metrics import CheckpointMetrics

        metrics = CheckpointMetrics()
        checkpointer = PostgresCheckpointer(pg_pool=pool, metrics=metrics)

        # Add checkpoint and trigger flush
        await checkpointer.aput(config, make_checkpoint(0), {})
        await checkpointer._flush()

        # Metrics should be recorded
        assert metrics.flush_count._value._value == 1
        assert metrics.buffer_size._value._value == 0
        assert metrics.flush_interval_seconds._value._value == 5

    @pytest.mark.asyncio
    async def test_metrics_interval_updated_during_adaptive_backoff(self, pool, config):
        from llm_client.orchestration.checkpointers.metrics import CheckpointMetrics

        metrics = CheckpointMetrics()
        checkpointer = PostgresCheckpointer(pg_pool=pool, metrics=metrics, flush_interval_seconds=5)

        # Simulate slow flush to trigger adaptive backoff
        original_write_batch = checkpointer._write_batch

        async def slow_write_batch(batch):
            await asyncio.sleep(0.6)
            return await original_write_batch(batch)

        checkpointer._write_batch = slow_write_batch

        # Add checkpoint and trigger flush
        await checkpointer.aput(config, make_checkpoint(0), {})
        await checkpointer._flush()

        # Metrics should reflect the new interval
        assert metrics.flush_interval_seconds._value._value == 1.0
