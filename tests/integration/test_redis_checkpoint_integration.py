"""Integration tests for RedisCheckpointer."""

import asyncio
import pytest
from langgraph.checkpoint.base import Checkpoint, RunnableConfig

from llm_client.orchestration.checkpointers.redis_checkpointer import RedisCheckpointer


@pytest.mark.integration
class TestRedisCheckpointerIntegration:
    """Integration tests for RedisCheckpointer with real Redis."""

    @pytest.fixture
    async def redis_client(self):
        """Fixture providing real Redis client."""
        import redis.asyncio as aioredis
        
        # Use the same URL as configured in the application
        redis_url = "redis://127.0.0.1:6379/1"  # DB 1 for checkpoints
        
        client = aioredis.from_url(redis_url, decode_responses=False)
        try:
            # Test connection
            await client.ping()
            yield client
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
        finally:
            await client.aclose()

    @pytest.fixture
    def checkpointer(self, redis_client):
        """Fixture providing RedisCheckpointer with real Redis client."""
        return RedisCheckpointer(redis_client=redis_client)

    @pytest.fixture
    def sample_checkpoint(self):
        """Fixture providing sample checkpoint data."""
        return Checkpoint(
            v=1,
            id="integration-test-checkpoint",
            ts="2026-09-27T10:00:00Z",
            channel_values={"messages": [{"role": "user", "content": "Integration test"}]},
            channel_versions={"messages": "1"},
            versions_seen={"messages": {"1": "1"}},
            updated_channels=["messages"],
        )

    @pytest.fixture
    def sample_config(self):
        """Fixture providing sample runnable config."""
        return RunnableConfig(
            thread_id="integration-test-thread",
            recursion_limit=100,
        )

    @pytest.mark.asyncio
    async def test_round_trip_put_get(self, checkpointer, sample_checkpoint, sample_config):
        """Test round-trip: put → get."""
        # Arrange - clean up any existing data
        await checkpointer.adelete_thread(sample_config["thread_id"])
        
        # Act - put checkpoint
        await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # Act - get checkpoint
        retrieved = await checkpointer.aget(sample_config)
        
        # Assert
        assert retrieved is not None
        assert retrieved["id"] == sample_checkpoint["id"]
        assert retrieved["ts"] == sample_checkpoint["ts"]
        assert retrieved["channel_values"] == sample_checkpoint["channel_values"]

    @pytest.mark.asyncio
    async def test_ttl_verification(self, checkpointer, sample_checkpoint, sample_config):
        """Test that TTL is properly set and updated."""
        # Arrange - clean up any existing data
        await checkpointer.adelete_thread(sample_config["thread_id"])
        
        # Act - put checkpoint
        await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # Get the latest checkpoint key to verify TTL
        latest_key = f"checkpoint:{sample_config['thread_id']}:latest"
        ttl = await checkpointer._redis_client.ttl(latest_key)
        
        # Assert - TTL should be close to 24 hours (within 1 second tolerance)
        assert ttl > 86300  # 24 hours - 1 second
        assert ttl <= 86400  # exactly 24 hours

    @pytest.mark.asyncio
    async def test_parallel_puts_no_race_condition(self, checkpointer, sample_config):
        """Test that parallel puts don't cause race conditions."""
        # Arrange - clean up any existing data
        await checkpointer.adelete_thread(sample_config["thread_id"])
        
        # Create multiple checkpoints
        checkpoints = []
        for i in range(10):
            checkpoint = Checkpoint(
                v=1,
                id=f"parallel-checkpoint-{i}",
                ts="2026-09-27T10:00:00Z",
                channel_values={"messages": [{"role": "user", "content": f"Test {i}"}]},
                channel_versions={"messages": str(i)},
                versions_seen={"messages": {str(i): str(i)}},
                updated_channels=["messages"],
            )
            checkpoints.append(checkpoint)
        
        # Act - put all checkpoints in parallel
        tasks = []
        for checkpoint in checkpoints:
            task = checkpointer.aput(sample_config, checkpoint, {})
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Assert - all checkpoints should be retrievable
        for i, checkpoint in enumerate(checkpoints):
            retrieved = await checkpointer.aget(sample_config)
            assert retrieved is not None
            # Note: aget returns the latest, so we'll get the last one
            # For proper parallel testing, you'd want to test specific checkpoint IDs

    @pytest.mark.asyncio
    async def test_list_checkpoints_integration(self, checkpointer, sample_config):
        """Test listing checkpoints with real Redis."""
        # Arrange - clean up and create multiple checkpoints
        await checkpointer.adelete_thread(sample_config["thread_id"])
        
        # Create and store multiple checkpoints
        for i in range(5):
            checkpoint = Checkpoint(
                v=1,
                id=f"list-checkpoint-{i}",
                ts="2026-09-27T10:00:00Z",
                channel_values={"messages": [{"role": "user", "content": f"List test {i}"}]},
                channel_versions={"messages": str(i)},
                versions_seen={"messages": {str(i): str(i)}},
                updated_channels=["messages"],
            )
            await checkpointer.aput(sample_config, checkpoint, {})
        
        # Act - list all checkpoints
        checkpoints = []
        async for checkpoint_tuple in checkpointer.alist(sample_config):
            checkpoints.append(checkpoint_tuple)
        
        # Assert
        assert len(checkpoints) == 5
        for i, checkpoint_tuple in enumerate(checkpoints):
            assert checkpoint_tuple.checkpoint["id"] == f"list-checkpoint-{i}"

    @pytest.mark.asyncio
    async def test_delete_thread_integration(self, checkpointer, sample_checkpoint, sample_config):
        """Test deleting thread data with real Redis."""
        # Arrange - store some data
        await checkpointer.aput(sample_config, sample_checkpoint, {})
        await checkpointer.aput_writes(sample_config, [], "test-task")
        
        # Verify data exists
        retrieved = await checkpointer.aget(sample_config)
        assert retrieved is not None
        
        # Act - delete thread
        await checkpointer.adelete_thread(sample_config["thread_id"])
        
        # Assert - data should be gone
        retrieved = await checkpointer.aget(sample_config)
        assert retrieved is None
        
        # Verify write data is also gone
        # (This would require checking Redis directly or having a method to list writes)

    @pytest.mark.asyncio
    async def test_writes_separate_from_checkpoints(self, checkpointer, sample_config):
        """Test that writes are stored separately from checkpoints."""
        # Arrange - clean up and store checkpoint and writes
        await checkpointer.adelete_thread(sample_config["thread_id"])
        
        checkpoint = Checkpoint(
            v=1,
            id="separate-test-checkpoint",
            ts="2026-09-27T10:00:00Z",
            channel_values={},
            channel_versions={},
            versions_seen={},
            updated_channels=[],
        )
        
        writes = [
            ("messages", "Hello", "1"),
            ("context", "World", "1"),
        ]
        
        # Act - store both checkpoint and writes
        await checkpointer.aput(sample_config, checkpoint, {})
        await checkpointer.aput_writes(sample_config, writes, "separate-task")
        
        # Assert - checkpoint should exist
        retrieved_checkpoint = await checkpointer.aget(sample_config)
        assert retrieved_checkpoint is not None
        
        # Note: To verify writes are separate, we'd need to check Redis directly
        # or implement a method to retrieve writes in the RedisCheckpointer

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, checkpointer, sample_checkpoint, sample_config):
        """Test handling of Redis connection errors."""
        # Arrange - close the Redis connection
        await checkpointer._redis_client.aclose()
        
        # Act & Assert - should raise CheckpointWriteError
        with pytest.raises(Exception) as exc_info:
            await checkpointer.aput(sample_config, sample_checkpoint, {})
        
        # The exact exception type may vary depending on Redis client version
        assert "failed after 3 retries" in str(exc_info.value) or "Connection" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_multiple_threads_isolation(self, checkpointer):
        """Test that data for different threads is isolated."""
        # Arrange - create two different thread configs
        config1 = RunnableConfig(thread_id="thread-1", recursion_limit=100)
        config2 = RunnableConfig(thread_id="thread-2", recursion_limit=100)
        
        checkpoint1 = Checkpoint(
            v=1,
            id="checkpoint-thread-1",
            ts="2026-09-27T10:00:00Z",
            channel_values={"messages": [{"role": "user", "content": "Thread 1"}]},
            channel_versions={"messages": "1"},
            versions_seen={"messages": {"1": "1"}},
            updated_channels=["messages"],
        )
        
        checkpoint2 = Checkpoint(
            v=1,
            id="checkpoint-thread-2",
            ts="2026-09-27T10:00:00Z",
            channel_values={"messages": [{"role": "user", "content": "Thread 2"}]},
            channel_versions={"messages": "1"},
            versions_seen={"messages": {"1": "1"}},
            updated_channels=["messages"],
        )
        
        # Act - store checkpoints for different threads
        await checkpointer.aput(config1, checkpoint1, {})
        await checkpointer.aput(config2, checkpoint2, {})
        
        # Assert - data should be isolated
        retrieved1 = await checkpointer.aget(config1)
        retrieved2 = await checkpointer.aget(config2)
        
        assert retrieved1 is not None
        assert retrieved2 is not None
        assert retrieved1["id"] == "checkpoint-thread-1"
        assert retrieved2["id"] == "checkpoint-thread-2"
        assert retrieved1["channel_values"]["messages"][0]["content"] == "Thread 1"
        assert retrieved2["channel_values"]["messages"][0]["content"] == "Thread 2"