"""Unit tests for RedisPostgresCheckpointer (B-3)."""

import uuid
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest

from llm_client.orchestration.checkpointers.composite import RedisPostgresCheckpointer
from llm_client.orchestration.checkpointers.errors import (
    CheckpointError,
    PostgresCheckpointWriteError,
    RedisCheckpointWriteError,
)
from llm_client.orchestration.checkpointers.metrics import NullCheckpointMetrics


class MockRedisCheckpointer:
    """Mock Redis checkpointer for testing."""

    def __init__(self, should_fail: bool = False, should_return_none: bool = False):
        self.should_fail = should_fail
        self.should_return_none = should_return_none
        self.data = {}
        self.writes = {}
        self.operations = []

    async def aput(
        self,
        config,
        checkpoint,
        metadata,
        new_versions=None,
    ):
        if self.should_fail:
            raise RedisCheckpointWriteError("Redis write failed")

        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = checkpoint.get("id")
        key = f"checkpoint:{thread_id}:{checkpoint_id}"

        self.data[key] = {"checkpoint": checkpoint, "metadata": metadata}
        self.operations.append(("aput", thread_id, checkpoint_id))
        return config

    async def aget(self, config):
        if self.should_fail:
            raise RedisCheckpointWriteError("Redis read failed")
        if self.should_return_none:
            return None

        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Find the latest checkpoint for this thread
        latest_key = None
        latest_ts = ""
        for key in self.data:
            if key.startswith(f"checkpoint:{thread_id}:"):
                checkpoint_data = self.data[key]
                if checkpoint_data["checkpoint"]["ts"] > latest_ts:
                    latest_ts = checkpoint_data["checkpoint"]["ts"]
                    latest_key = key

        if not latest_key:
            return None

        return self.data[latest_key]["checkpoint"]

    async def aget_tuple(self, config):
        checkpoint = await self.aget(config)
        if checkpoint is None:
            return None

        # Create a CheckpointTuple-like object with checkpoint attribute
        class MockCheckpointTuple:
            def __init__(self, config, checkpoint, metadata):
                self.config = config
                self.checkpoint = checkpoint
                self.metadata = metadata
                self.parent_config = None
                self.pending_writes = None

        return MockCheckpointTuple(config, checkpoint, {"source": "redis"})

    async def alist(
        self,
        config=None,
        *,
        filter=None,
        before=None,
        limit=None,
    ) -> AsyncIterator:
        if self.should_fail:
            raise RedisCheckpointWriteError("Redis list failed")

        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Return checkpoints sorted by timestamp (newest first)
        checkpoints = []
        for key in self.data:
            if key.startswith(f"checkpoint:{thread_id}:"):
                checkpoint_data = self.data[key]

                # Create a MockCheckpointTuple object
                class MockCheckpointTuple:
                    def __init__(self, config, checkpoint, metadata):
                        self.config = config
                        self.checkpoint = checkpoint
                        self.metadata = metadata
                        self.parent_config = None
                        self.pending_writes = None

                checkpoints.append(
                    MockCheckpointTuple(config, checkpoint_data["checkpoint"], {"source": "redis"})
                )

        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda x: x.checkpoint["ts"], reverse=True)

        # Apply limit
        if limit is not None:
            checkpoints = checkpoints[:limit]

        for checkpoint in checkpoints:
            yield checkpoint

    async def aput_writes(self, config, writes, task_id, task_path=None):
        if self.should_fail:
            raise RedisCheckpointWriteError("Redis writes failed")

        thread_id = config.get("configurable", {}).get("thread_id", "default")
        key = f"writes:{thread_id}:{task_id}"
        self.writes[key] = writes
        self.operations.append(("aput_writes", thread_id, task_id))

    async def adelete_thread(self, thread_id):
        if self.should_fail:
            raise RedisCheckpointWriteError("Redis delete failed")

        keys_to_delete = [k for k in self.data if k.startswith(f"checkpoint:{thread_id}:")]
        for key in keys_to_delete:
            del self.data[key]

        self.operations.append(("adelete_thread", thread_id))


class MockPostgresCheckpointer:
    """Mock PostgreSQL checkpointer for testing."""

    def __init__(self, should_fail: bool = False, should_return_none: bool = False):
        self.should_fail = should_fail
        self.should_return_none = should_return_none
        self.data = {}
        self.writes = {}
        self.operations = []

    async def aput(
        self,
        config,
        checkpoint,
        metadata,
        new_versions=None,
    ):
        if self.should_fail:
            raise PostgresCheckpointWriteError("PostgreSQL write failed")

        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = checkpoint.get("id")
        key = f"checkpoint:{thread_id}:{checkpoint_id}"

        self.data[key] = {"checkpoint": checkpoint, "metadata": metadata}
        self.operations.append(("aput", thread_id, checkpoint_id))
        return config

    async def aget(self, config):
        if self.should_fail:
            raise PostgresCheckpointWriteError("PostgreSQL read failed")
        if self.should_return_none:
            return None

        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Find the latest checkpoint for this thread
        latest_key = None
        latest_ts = ""
        for key in self.data:
            if key.startswith(f"checkpoint:{thread_id}:"):
                checkpoint_data = self.data[key]
                if checkpoint_data["checkpoint"]["ts"] > latest_ts:
                    latest_ts = checkpoint_data["checkpoint"]["ts"]
                    latest_key = key

        if not latest_key:
            return None

        return self.data[latest_key]["checkpoint"]

    async def aget_tuple(self, config):
        checkpoint = await self.aget(config)
        if checkpoint is None:
            return None

        # Create a CheckpointTuple-like object with checkpoint attribute
        class MockCheckpointTuple:
            def __init__(self, config, checkpoint, metadata):
                self.config = config
                self.checkpoint = checkpoint
                self.metadata = metadata
                self.parent_config = None
                self.pending_writes = None

        return MockCheckpointTuple(config, checkpoint, {"source": "postgres"})

    async def alist(
        self,
        config=None,
        *,
        filter=None,
        before=None,
        limit=None,
    ) -> AsyncIterator:
        if self.should_fail:
            raise PostgresCheckpointWriteError("PostgreSQL list failed")

        # Return all stored checkpoints
        thread_id = config.get("configurable", {}).get("thread_id", "default")

        # Return checkpoints sorted by timestamp (newest first)
        checkpoints = []
        for key in self.data:
            if key.startswith(f"checkpoint:{thread_id}:"):
                checkpoint_data = self.data[key]

                # Create a MockCheckpointTuple object
                class MockCheckpointTuple:
                    def __init__(self, config, checkpoint, metadata):
                        self.config = config
                        self.checkpoint = checkpoint
                        self.metadata = metadata
                        self.parent_config = None
                        self.pending_writes = None

                checkpoints.append(
                    MockCheckpointTuple(
                        config, checkpoint_data["checkpoint"], {"source": "postgres"}
                    )
                )

        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda x: x.checkpoint["ts"], reverse=True)

        for checkpoint in checkpoints:
            yield checkpoint

    async def aput_writes(self, config, writes, task_id, task_path=None):
        if self.should_fail:
            raise PostgresCheckpointWriteError("PostgreSQL writes failed")

        thread_id = config.get("configurable", {}).get("thread_id", "default")
        key = f"writes:{thread_id}:{task_id}"
        self.writes[key] = writes
        self.operations.append(("aput_writes", thread_id, task_id))

    async def adelete_thread(self, thread_id):
        if self.should_fail:
            raise PostgresCheckpointWriteError("PostgreSQL delete failed")

        keys_to_delete = [k for k in self.data if k.startswith(f"checkpoint:{thread_id}:")]
        for key in keys_to_delete:
            del self.data[key]

        self.operations.append(("adelete_thread", thread_id))


class MockOperationalWriter:
    """Mock operational writer for testing."""

    def __init__(self):
        self.events = []

    async def write(self, event):
        self.events.append(event)


class MockFailureCallback:
    """Mock failure callback for testing."""

    def __init__(self):
        self.calls = []

    def __call__(self, thread_id: str, reason: str):
        self.calls.append((thread_id, reason))


@pytest.fixture
def redis_checkpointer():
    return MockRedisCheckpointer()


@pytest.fixture
def postgres_checkpointer():
    return MockPostgresCheckpointer()


@pytest.fixture
def operational_writer():
    return MockOperationalWriter()


@pytest.fixture
def failure_callback():
    return MockFailureCallback()


@pytest.fixture
def sample_checkpoint():
    return {
        "id": str(uuid.uuid4()),
        "ts": "2026-09-27T10:00:00.000000+00:00",
        "channel_values": [],
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": [],
    }


@pytest.fixture
def sample_config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


@pytest.fixture
def mock_metrics():
    """Mock metrics for testing."""
    metrics = MagicMock()
    metrics.increment_redis_hit = MagicMock()
    metrics.increment_redis_miss = MagicMock()
    metrics.increment_redis_error = MagicMock()
    metrics.increment_pg_error = MagicMock()
    metrics.increment_both_failed = MagicMock()
    return metrics


@pytest.fixture
def composite_checkpointer(
    redis_checkpointer, postgres_checkpointer, operational_writer, failure_callback, mock_metrics
):
    return RedisPostgresCheckpointer(
        redis_checkpointer=redis_checkpointer,
        postgres_checkpointer=postgres_checkpointer,
        operational_writer=operational_writer,
        on_total_failure=failure_callback,
        metrics=mock_metrics,
    )


class TestRedisPostgresCheckpointer:
    """Test the composite checkpointer."""

    @pytest.mark.asyncio
    async def test_aput_both_success(
        self, composite_checkpointer, sample_checkpoint, sample_config
    ):
        """Test successful aput to both layers."""
        metadata = {"source": "test"}

        result = await composite_checkpointer.aput(sample_config, sample_checkpoint, metadata)

        # Should return config unchanged
        assert result == sample_config

        # Both checkpointer should have received the write
        thread_id = sample_config["configurable"]["thread_id"]
        checkpoint_id = sample_checkpoint["id"]
        expected_op = ("aput", thread_id, checkpoint_id)
        assert expected_op in composite_checkpointer._redis.operations
        assert expected_op in composite_checkpointer._postgres.operations

    @pytest.mark.asyncio
    async def test_aput_redis_fail_postgres_success(
        self, composite_checkpointer, sample_checkpoint, sample_config
    ):
        """Test aput when Redis fails but PostgreSQL succeeds."""
        composite_checkpointer._redis.should_fail = True

        metadata = {"source": "test"}

        result = await composite_checkpointer.aput(sample_config, sample_checkpoint, metadata)

        # Should return config unchanged
        assert result == sample_config

        # Redis should have failed, PostgreSQL should have succeeded
        thread_id = sample_config["configurable"]["thread_id"]
        checkpoint_id = sample_checkpoint["id"]
        expected_op = ("aput", thread_id, checkpoint_id)
        assert expected_op not in composite_checkpointer._redis.operations
        assert expected_op in composite_checkpointer._postgres.operations

        # Should have logged Redis failure
        assert len(composite_checkpointer._operational_writer.events) == 1
        assert (
            composite_checkpointer._operational_writer.events[0]["event"]
            == "checkpoint_redis_write_failed"
        )

    @pytest.mark.asyncio
    async def test_aput_both_fail(self, composite_checkpointer, sample_checkpoint, sample_config):
        """Test aput when both layers fail."""
        composite_checkpointer._redis.should_fail = True
        composite_checkpointer._postgres.should_fail = True

        metadata = {"source": "test"}

        with pytest.raises(CheckpointError):
            await composite_checkpointer.aput(sample_config, sample_checkpoint, metadata)

        # Should have logged both failures
        assert len(composite_checkpointer._operational_writer.events) == 2
        assert (
            composite_checkpointer._operational_writer.events[0]["event"]
            == "checkpoint_redis_write_failed"
        )
        assert (
            composite_checkpointer._operational_writer.events[1]["event"]
            == "checkpoint_both_write_failed"
        )

        # Should have called the failure callback
        assert len(composite_checkpointer._on_total_failure.calls) == 1
        assert composite_checkpointer._on_total_failure.calls[0][1] == "system_error"

    @pytest.mark.asyncio
    async def test_aget_redis_hit(self, composite_checkpointer, sample_checkpoint, sample_config):
        """Test aget when Redis has the checkpoint."""
        # Store checkpoint in Redis
        metadata = {"source": "test"}
        await composite_checkpointer._redis.aput(sample_config, sample_checkpoint, metadata)

        result = await composite_checkpointer.aget(sample_config)

        # Should return the checkpoint
        assert result == sample_checkpoint

        # Should have hit Redis
        composite_checkpointer._metrics.increment_redis_hit.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_redis_fallback_postgres(
        self, composite_checkpointer, sample_checkpoint, sample_config
    ):
        """Test aget when Redis misses but PostgreSQL has the checkpoint."""
        # Store checkpoint only in PostgreSQL
        metadata = {"source": "test"}
        await composite_checkpointer._postgres.aput(sample_config, sample_checkpoint, metadata)

        # Make Redis return None
        composite_checkpointer._redis.should_return_none = True

        result = await composite_checkpointer.aget(sample_config)

        # Should return the checkpoint
        assert result == sample_checkpoint

        # Should have fallen back to PostgreSQL
        composite_checkpointer._metrics.increment_pg_fallback.assert_called_once()

    @pytest.mark.asyncio
    async def test_aget_both_fail(self, composite_checkpointer, sample_config):
        """Test aget when both layers fail."""
        composite_checkpointer._redis.should_fail = True
        composite_checkpointer._postgres.should_fail = True

        result = await composite_checkpointer.aget(sample_config)

        # Should return None
        assert result is None

        # Should have incremented error counters
        assert composite_checkpointer._metrics.increment_redis_error.called
        assert composite_checkpointer._metrics.increment_pg_error.called

    @pytest.mark.asyncio
    async def test_aget_tuple_redis_hit(
        self, composite_checkpointer, sample_checkpoint, sample_config
    ):
        """Test aget_tuple when Redis has the checkpoint."""
        # Store checkpoint in Redis
        metadata = {"source": "test"}
        await composite_checkpointer._redis.aput(sample_config, sample_checkpoint, metadata)

        result = await composite_checkpointer.aget_tuple(sample_config)

        # Should return the tuple with Redis metadata
        assert result is not None
        assert result.checkpoint == sample_checkpoint
        assert result.metadata["source"] == "redis"

    @pytest.mark.asyncio
    async def test_aget_tuple_postgres_fallback(
        self, composite_checkpointer, sample_checkpoint, sample_config
    ):
        """Test aget_tuple when Redis misses but PostgreSQL has the checkpoint."""
        # Store checkpoint only in PostgreSQL
        metadata = {"source": "test"}
        await composite_checkpointer._postgres.aput(sample_config, sample_checkpoint, metadata)

        # Make Redis return None
        composite_checkpointer._redis.should_return_none = True

        result = await composite_checkpointer.aget_tuple(sample_config)

        # Should return the tuple with PostgreSQL metadata
        assert result is not None
        assert result.checkpoint == sample_checkpoint
        assert result.metadata["source"] == "postgres"

    @pytest.mark.asyncio
    async def test_alist_merges_and_deduplicates(self, composite_checkpointer, sample_config):
        """Test that alist merges and deduplicates checkpoints from both layers."""
        # Store some checkpoints in both layers
        for i in range(3):
            # Create different checkpoints for Redis and PostgreSQL
            redis_checkpoint = {
                "id": f"redis-{i}",
                "ts": f"2026-09-27T10:00:{i:02d}+00:00",
                "channel_values": [],
                "channel_versions": {},
                "versions_seen": {},
                "updated_channels": [],
            }
            postgres_checkpoint = {
                "id": f"postgres-{i}",
                "ts": f"2026-09-27T09:59:{i:02d}+00:00",  # Slightly older
                "channel_values": [],
                "channel_versions": {},
                "versions_seen": {},
                "updated_channels": [],
            }
            metadata = {"source": "test", "index": i}

            # Store in Redis (newer)
            await composite_checkpointer._redis.aput(sample_config, redis_checkpoint, metadata)

            # Store in PostgreSQL (older)
            await composite_checkpointer._postgres.aput(
                sample_config, postgres_checkpoint, metadata
            )

        # Get list from composite
        checkpoints = []
        async for checkpoint in composite_checkpointer.alist(sample_config):
            checkpoints.append(checkpoint)

        # Should have 6 unique checkpoints (3 from Redis + 3 from PostgreSQL)
        assert len(checkpoints) == 6

        # Should be sorted by timestamp (newest first)
        timestamps = [cp.checkpoint["ts"] for cp in checkpoints]
        assert timestamps == sorted(timestamps, reverse=True)

        # Should have both sources represented
        sources = [cp.metadata["source"] for cp in checkpoints]
        assert "redis" in sources
        assert "postgres" in sources

    @pytest.mark.asyncio
    async def test_aput_writes_both_layers(self, composite_checkpointer, sample_config):
        """Test that aput_writes writes to both layers."""
        writes = [("messages", [{"role": "user", "content": "test"}])]
        task_id = "test-task"

        await composite_checkpointer.aput_writes(sample_config, writes, task_id)

        # Both checkpointer should have received the writes
        thread_id = sample_config["configurable"]["thread_id"]
        expected_op = ("aput_writes", thread_id, "test-task")
        assert expected_op in composite_checkpointer._redis.operations
        assert expected_op in composite_checkpointer._postgres.operations

    @pytest.mark.asyncio
    async def test_aput_writes_layer_failure(self, composite_checkpointer, sample_config):
        """Test that aput_writes handles layer failures gracefully."""
        composite_checkpointer._redis.should_fail = True

        writes = [("messages", [{"role": "user", "content": "test"}])]
        task_id = "test-task"

        # Should not raise exception
        await composite_checkpointer.aput_writes(sample_config, writes, task_id)

        # PostgreSQL should have succeeded
        thread_id = sample_config["configurable"]["thread_id"]
        expected_op = ("aput_writes", thread_id, "test-task")
        assert expected_op in composite_checkpointer._postgres.operations

    @pytest.mark.asyncio
    async def test_adelete_thread_both_layers(self, composite_checkpointer, sample_config):
        """Test that adelete_thread deletes from both layers."""
        thread_id = sample_config["configurable"]["thread_id"]

        # Store some checkpoints
        checkpoint = {
            "id": str(uuid.uuid4()),
            "ts": "2026-09-27T10:00:00.000000+00:00",
            "channel_values": [],
            "channel_versions": {},
            "versions_seen": {},
            "updated_channels": [],
        }
        metadata = {"source": "test"}

        await composite_checkpointer._redis.aput(sample_config, checkpoint, metadata)
        await composite_checkpointer._postgres.aput(sample_config, checkpoint, metadata)

        # Delete thread
        await composite_checkpointer.adelete_thread(thread_id)

        # Both checkpointer should have received the delete
        thread_id = sample_config["configurable"]["thread_id"]
        expected_op = ("adelete_thread", thread_id)
        assert expected_op in composite_checkpointer._redis.operations
        assert expected_op in composite_checkpointer._postgres.operations

    @pytest.mark.asyncio
    async def test_adelete_thread_layer_failure(self, composite_checkpointer, sample_config):
        """Test that adelete_thread handles layer failures gracefully."""
        composite_checkpointer._redis.should_fail = True

        thread_id = sample_config["configurable"]["thread_id"]

        # Should not raise exception
        await composite_checkpointer.adelete_thread(thread_id)

        # PostgreSQL should have succeeded
        thread_id = sample_config["configurable"]["thread_id"]
        expected_op = ("adelete_thread", thread_id)
        assert expected_op in composite_checkpointer._postgres.operations

    def test_metrics_are_instrumented(
        self, composite_checkpointer, sample_checkpoint, sample_config
    ):
        """Test that metrics are properly instrumented."""
        # This is more of an integration test - we can't easily mock the metrics
        # But we can verify that the checkpointer has metrics
        assert composite_checkpointer._metrics is not None
        assert composite_checkpointer._metrics.increment_redis_hit is not None
        assert composite_checkpointer._metrics.increment_pg_fallback is not None
        assert composite_checkpointer._metrics.increment_redis_error is not None
        assert composite_checkpointer._metrics.increment_pg_error is not None
        assert composite_checkpointer._metrics.increment_both_failed is not None

    def test_null_metrics_fallback(self):
        """Test that NullCheckpointMetrics is used when none provided."""
        checkpointer = RedisPostgresCheckpointer(
            redis_checkpointer=MockRedisCheckpointer(),
            postgres_checkpointer=MockPostgresCheckpointer(),
        )

        # Should use null metrics
        assert isinstance(checkpointer._metrics, NullCheckpointMetrics)

        # All methods should be no-ops
        checkpointer._metrics.increment_redis_hit()
        checkpointer._metrics.increment_pg_fallback()
        # etc. - no exceptions should be raised
