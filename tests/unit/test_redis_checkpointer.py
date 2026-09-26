"""Unit tests for RedisCheckpointer."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis import asyncio as aioredis
from langgraph.checkpoint.base import (
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
)

from llm_client.orchestration.checkpointers.errors import CheckpointWriteError
from llm_client.orchestration.checkpointers.redis_checkpointer import RedisCheckpointer


class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.data = {}
        self.operations = []
    
    async def set(self, key: str, value: str | bytes, ex: int = None) -> None:
        """Mock SET command."""
        self.operations.append(("set", key, ex))
        self.data[key] = value
    
    async def get(self, key: str) -> str | None:
        """Mock GET command."""
        self.operations.append(("get", key))
        return self.data.get(key)
    
    async def delete(self, key: str) -> None:
        """Mock DELETE command."""
        self.operations.append(("delete", key))
        self.data.pop(key, None)
    
    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[str]]:
        """Mock SCAN command."""
        self.operations.append(("scan", match))
        matching_keys = [k for k in self.data.keys() if k.startswith(match.replace("*", ""))]
        return 0, matching_keys


@pytest.fixture
def mock_redis_client():
    """Fixture providing mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def checkpointer(mock_redis_client):
    """Fixture providing RedisCheckpointer with mock client."""
    return RedisCheckpointer(redis_client=mock_redis_client)


@pytest.fixture
def sample_checkpoint():
    """Fixture providing sample checkpoint data."""
    return Checkpoint(
        v=1,
        id="test-checkpoint-123",
        ts="2026-09-27T10:00:00Z",
        channel_values={"messages": [{"role": "user", "content": "Hello"}]},
        channel_versions={"messages": "1"},
        versions_seen={"messages": {"1": "1"}},
        updated_channels=["messages"],
    )


@pytest.fixture
def sample_config():
    """Fixture providing sample runnable config."""
    return RunnableConfig(
        thread_id="test-thread-456",
        recursion_limit=100,
    )


class TestRedisCheckpointer:
    """Test suite for RedisCheckpointer."""

    @pytest.mark.asyncio
    async def test_aput_stores_checkpoint(self, checkpointer, sample_checkpoint, sample_config):
        """Test that aput stores checkpoint with correct key and TTL."""
        # Act
        result = await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # Assert
        assert result == sample_config
        
        # Verify checkpoint was stored
        expected_key = "checkpoint:test-thread-456:test-checkpoint-123"
        assert expected_key in checkpointer._redis_client.data
        
        # Verify latest index was updated
        latest_key = "checkpoint:test-thread-456:latest"
        assert latest_key in checkpointer._redis_client.data
        assert checkpointer._redis_client.data[latest_key] == "test-checkpoint-123"
        
        # Verify TTL was set
        set_operations = [op for op in checkpointer._redis_client.operations if op[0] == "set"]
        assert len(set_operations) == 2  # checkpoint + latest index
        for op in set_operations:
            assert op[2] == 86400  # TTL

    @pytest.mark.asyncio
    async def test_aget_retrieves_checkpoint(self, checkpointer, sample_checkpoint, sample_config):
        """Test that aget retrieves stored checkpoint."""
        # Arrange - store checkpoint first
        await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # Act
        retrieved = await checkpointer.aget(sample_config)
        
        # Assert
        assert retrieved is not None
        assert retrieved["id"] == sample_checkpoint["id"]
        assert retrieved["ts"] == sample_checkpoint["ts"]

    @pytest.mark.asyncio
    async def test_aget_returns_none_for_missing_checkpoint(self, checkpointer, sample_config):
        """Test that aget returns None when no checkpoint exists."""
        # Act
        result = await checkpointer.aget(sample_config)
        
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_aget_tuple_returns_checkpoint_tuple(self, checkpointer, sample_checkpoint, sample_config):
        """Test that aget_tuple returns CheckpointTuple."""
        # Arrange - store checkpoint first
        await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # Act
        result = await checkpointer.aget_tuple(sample_config)
        
        # Assert
        assert result is not None
        assert isinstance(result, CheckpointTuple)
        assert result.config == sample_config
        assert result.checkpoint == sample_checkpoint
        assert result.metadata == {}

    @pytest.mark.asyncio
    async def test_aget_tuple_returns_none_for_missing_checkpoint(self, checkpointer, sample_config):
        """Test that aget_tuple returns None when no checkpoint exists."""
        # Act
        result = await checkpointer.aget_tuple(sample_config)
        
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_alist_iterates_checkpoints(self, checkpointer, sample_checkpoint, sample_config):
        """Test that alist iterates through checkpoints."""
        # Arrange - store multiple checkpoints
        for i in range(3):
            checkpoint = Checkpoint(
                v=1,
                id=f"checkpoint-{i}",
                ts="2026-09-27T10:00:00Z",
                channel_values={},
                channel_versions={},
                versions_seen={},
                updated_channels=[],
            )
            await checkpointer.aput(sample_config, checkpoint, {})
        
        # Act
        checkpoints = []
        async for checkpoint_tuple in checkpointer.alist(sample_config):
            checkpoints.append(checkpoint_tuple)
        
        # Assert
        assert len(checkpoints) == 3
        for i, checkpoint_tuple in enumerate(checkpoints):
            assert checkpoint_tuple.checkpoint["id"] == f"checkpoint-{i}"

    @pytest.mark.asyncio
    async def test_alist_with_limit(self, checkpointer, sample_checkpoint, sample_config):
        """Test that alist respects limit parameter."""
        # Arrange - store multiple checkpoints
        for i in range(5):
            checkpoint = Checkpoint(
                v=1,
                id=f"checkpoint-{i}",
                ts="2026-09-27T10:00:00Z",
                channel_values={},
                channel_versions={},
                versions_seen={},
                updated_channels=[],
            )
            await checkpointer.aput(sample_config, checkpoint, {})
        
        # Act
        checkpoints = []
        async for checkpoint_tuple in checkpointer.alist(sample_config, limit=2):
            checkpoints.append(checkpoint_tuple)
        
        # Assert
        assert len(checkpoints) == 2

    @pytest.mark.asyncio
    async def test_aput_writes_stores_separately(self, checkpointer, sample_config):
        """Test that aput_writes stores writes in separate keys."""
        # Arrange
        writes = [
            ("messages", "Hello"),
            ("context", "World"),
        ]
        
        # Act
        await checkpointer.aput_writes(sample_config, writes, "task-123")
        
        # Assert
        expected_key = "writes:test-thread-456:task-123"
        assert expected_key in checkpointer._redis_client.data
        stored_writes = json.loads(checkpointer._redis_client.data[expected_key])
        # Convert stored lists back to tuples for comparison
        expected_writes_as_lists = [[str(ch), val] for ch, val in writes]
        assert stored_writes == expected_writes_as_lists

    @pytest.mark.asyncio
    async def test_adelete_thread_removes_all_data(self, checkpointer, sample_checkpoint, sample_config):
        """Test that adelete_thread removes all checkpoints and writes."""
        # Arrange - store data
        await checkpointer.aput(sample_config, sample_checkpoint, {})
        await checkpointer.aput_writes(sample_config, [], "task-123")
        
        # Verify data exists
        assert "checkpoint:test-thread-456:test-checkpoint-123" in checkpointer._redis_client.data
        assert "writes:test-thread-456:task-123" in checkpointer._redis_client.data
        
        # Act
        await checkpointer.adelete_thread("test-thread-456")
        
        # Assert
        assert "checkpoint:test-thread-456:test-checkpoint-123" not in checkpointer._redis_client.data
        assert "writes:test-thread-456:task-123" not in checkpointer._redis_client.data
        assert "checkpoint:test-thread-456:latest" not in checkpointer._redis_client.data

    @pytest.mark.asyncio
    async def test_retry_logic_succeeds_after_failure(self, checkpointer, sample_checkpoint, sample_config):
        """Test that retry logic eventually succeeds."""
        # Arrange - mock Redis to fail once, then succeed
        original_set = checkpointer._redis_client.set
        call_count = 0
        
        async def mock_set(key: str, value: str | bytes, ex: int = None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Raise a Redis-specific exception that will be retried
                raise aioredis.ConnectionError("Connection failed")
            return await original_set(key, value, ex)
        
        checkpointer._redis_client.set = mock_set
        
        # Act
        await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # Assert - should have succeeded after retry
        # Note: there are 2 Redis calls per aput (checkpoint + latest index)
        # First call fails, then 2 retries succeed = 3 total calls
        assert call_count == 3  # 1 failure + 2 successes
        expected_key = "checkpoint:test-thread-456:test-checkpoint-123"
        assert expected_key in checkpointer._redis_client.data

    @pytest.mark.asyncio
    async def test_retry_logic_raises_after_max_attempts(self, checkpointer, sample_checkpoint, sample_config):
        """Test that retry logic raises CheckpointWriteError after max attempts."""
        # Arrange - mock Redis to always fail
        async def mock_set(key: str, value: str | bytes, ex: int = None):
            import redis.asyncio as aioredis
            raise aioredis.ConnectionError("Persistent failure")
        
        checkpointer._redis_client.set = mock_set
        
        # Act & Assert
        with pytest.raises(CheckpointWriteError) as exc_info:
            await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # The error message should indicate Redis operation failed
        assert "Redis operation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_custom_ttl_setting(self, mock_redis_client):
        """Test that custom TTL is used when specified."""
        # Arrange
        custom_ttl = 3600  # 1 hour
        checkpointer = RedisCheckpointer(mock_redis_client, ttl_seconds=custom_ttl)
        checkpoint = Checkpoint(v=1, id="test", ts="2026-09-27T10:00:00Z", channel_values={}, channel_versions={}, versions_seen={}, updated_channels=[])
        config = RunnableConfig(thread_id="test-thread")
        
        # Act
        await checkpointer.aput(config, checkpoint, {})
        
        # Assert
        set_operations = [op for op in mock_redis_client.operations if op[0] == "set"]
        for op in set_operations:
            assert op[2] == custom_ttl

    @pytest.mark.asyncio
    async def test_scan_keys_lazy_iteration(self, checkpointer, sample_config):
        """Test that _scan_keys performs lazy iteration."""
        # Arrange - store some data
        for i in range(5):
            checkpoint = Checkpoint(
                v=1,
                id=f"checkpoint-{i}",
                ts="2026-09-27T10:00:00Z",
                channel_values={},
                channel_versions={},
                versions_seen={},
                updated_channels=[],
            )
            await checkpointer.aput(sample_config, checkpoint, {})
        
        # Act
        keys = []
        async for key in checkpointer._scan_keys("checkpoint:test-thread-456:*"):
            keys.append(key)
        
        # Assert
        assert len(keys) == 5
        for i, key in enumerate(keys):
            assert f"checkpoint-{i}" in key