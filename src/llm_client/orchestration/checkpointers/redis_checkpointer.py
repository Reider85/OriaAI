"""Redis-based checkpoint saver for LangGraph."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import redis.asyncio as aioredis
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
    SerializerProtocol,
)

from .errors import CheckpointWriteError


def _get_thread_id(config: RunnableConfig) -> str:
    """Extract thread_id from RunnableConfig, with fallback to 'default'.

    LangGraph passes thread_id in config["configurable"]["thread_id"].
    Falls back to a top-level config["thread_id"] or 'default' if not found.
    """
    configurable = config.get("configurable") or {}
    if "thread_id" in configurable:
        return configurable["thread_id"]
    thread_id = config.get("thread_id")
    return str(thread_id) if thread_id else "default"


class RedisCheckpointer(BaseCheckpointSaver):
    """Synchronous Redis-based checkpoint saver with TTL.
    
    Implements LangGraph's BaseCheckpointSaver interface, writing checkpoints
    synchronously to Redis DB 1 with TTL=24h. Designed for ADR-10 async checkpointing.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        ttl_seconds: int = 86400,
        serde: SerializerProtocol | None = None,
        metrics: Any = None,
    ) -> None:
        """Initialize Redis checkpointer.
        
        Args:
            redis_client: Async Redis client connected to DB 1 (checkpoint DB)
            ttl_seconds: TTL for checkpoint records (default: 86400 = 24h)
            serde: Optional serializer (default: JsonPlusSerializer from LangGraph)
        """
        super().__init__(serde=serde)
        self._redis_client = redis_client
        self._ttl_seconds = ttl_seconds
        self._metrics = metrics

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float] | None = None,
    ) -> RunnableConfig:
        """Store a checkpoint synchronously in Redis.
        
        Args:
            config: Runnable configuration containing thread_id
            checkpoint: Checkpoint data to store
            metadata: Checkpoint metadata
            new_versions: Optional channel version updates
            
        Returns:
            Updated config (pass-through)
            
        Raises:
            CheckpointWriteError: If Redis write fails after 3 retries
        """
        thread_id = _get_thread_id(config)
        checkpoint_id = checkpoint.get("id", "unknown")
        
        # Record write latency
        start_time = asyncio.get_event_loop().time()
        
        # Serialize checkpoint using LangGraph's serde
        serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        
        # Key pattern: checkpoint:{thread_id}:{checkpoint_id}
        key = f"checkpoint:{thread_id}:{checkpoint_id}"
        
        # Store checkpoint with TTL and update latest index
        # Include metadata for parity with postgres_checkpointer
        stored_value = json.dumps({
            'type': serialized_checkpoint[0],  # Already a string
            'data': serialized_checkpoint[1].hex(),  # Convert bytes to hex string
            'metadata': metadata,
        })
        await self._retry_redis_operation(
            lambda: self._store_checkpoint_with_ttl(key, stored_value)
        )
        
        # Update latest checkpoint index for this thread
        latest_key = f"checkpoint:{thread_id}:latest"
        await self._retry_redis_operation(
            lambda: self._redis_client.set(latest_key, checkpoint_id, ex=self._ttl_seconds)
        )
        
        # Record write latency metrics
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        if self._metrics:
            self._metrics.record_redis_write_latency(duration_ms)
        
        return config

    async def aget(
        self,
        config: RunnableConfig,
    ) -> Checkpoint | None:
        """Get the latest checkpoint for a thread.
        
        Args:
            config: Runnable configuration containing thread_id
            
        Returns:
            Checkpoint data or None if not found
        """
        thread_id = _get_thread_id(config)
        latest_key = f"checkpoint:{thread_id}:latest"

        latest_checkpoint_id = await self._redis_client.get(latest_key)
        if not latest_checkpoint_id:
            return None
            
        # Ensure we're working with string
        if isinstance(latest_checkpoint_id, bytes):
            latest_checkpoint_id = latest_checkpoint_id.decode()
            
        checkpoint_key = f"checkpoint:{thread_id}:{latest_checkpoint_id}"
        serialized_checkpoint = await self._redis_client.get(checkpoint_key)
        
        if not serialized_checkpoint:
            return None
            
        # Deserialize checkpoint using LangGraph's serde
        # The stored data is a JSON string with type and data (and metadata)
        stored_data = json.loads(serialized_checkpoint)
        serialization_type = stored_data['type']
        checkpoint_bytes = bytes.fromhex(stored_data['data'])
        
        # Record read metrics
        if self._metrics:
            self._metrics.increment_redis_hit()
        
        return self.serde.loads_typed((serialization_type, checkpoint_bytes))

    async def aget_tuple(
        self,
        config: RunnableConfig,
    ) -> CheckpointTuple | None:
        """Get the latest checkpoint tuple for a thread.
        
        Args:
            config: Runnable configuration containing thread_id
            
        Returns:
            CheckpointTuple or None if not found
        """
        thread_id = _get_thread_id(config)
        latest_key = f"checkpoint:{thread_id}:latest"
        
        latest_checkpoint_id = await self._redis_client.get(latest_key)
        if not latest_checkpoint_id:
            return None
            
        # Ensure we're working with string
        if isinstance(latest_checkpoint_id, bytes):
            latest_checkpoint_id = latest_checkpoint_id.decode()
            
        checkpoint_key = f"checkpoint:{thread_id}:{latest_checkpoint_id}"
        serialized_checkpoint = await self._redis_client.get(checkpoint_key)
        
        if not serialized_checkpoint:
            return None
            
        # Deserialize checkpoint using LangGraph's serde
        stored_data = json.loads(serialized_checkpoint)
        serialization_type = stored_data['type']
        checkpoint_bytes = bytes.fromhex(stored_data['data'])
        metadata = stored_data.get('metadata', {})  # Include stored metadata
        
        checkpoint = self.serde.loads_typed((serialization_type, checkpoint_bytes))
        
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=None,
            pending_writes=None,
        )

    async def alist(
        self,
        config: RunnableConfig | None = None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints for a thread.
        
        Args:
            config: Runnable configuration containing thread_id
            filter: Optional filter criteria
            before: Optional checkpoint_id to list before
            limit: Optional maximum number of checkpoints to return
            
        Yields:
            CheckpointTuple objects
        """
        if config is None:
            config = RunnableConfig()
        # Use a default thread_id if not provided
        if isinstance(config, dict):
            thread_id = config.get("thread_id", "default")
        else:
            # RunnableConfig is a TypedDict, access fields directly
            thread_id = config.get("thread_id", "default")
        pattern = f"checkpoint:{thread_id}:*"
        
        # Use Redis SCAN for lazy iteration
        async for key in self._scan_keys(pattern):
            # Skip 'latest' key
            key_str = key.decode() if isinstance(key, bytes) else key
            if key_str.endswith(":latest"):
                continue
                
            # Extract checkpoint_id from key
            key_str = key.decode() if isinstance(key, bytes) else key
            checkpoint_id = key_str.split(":")[-1]
            
            # Skip if 'before' specified and checkpoint_id is not before it
            if before and isinstance(before, str) and checkpoint_id >= before:
                continue
                
            serialized_checkpoint = await self._redis_client.get(key)
            if not serialized_checkpoint:
                continue
                
            # Deserialize checkpoint using LangGraph's serde
            # The stored data is a JSON string with type and data
            import json
            stored_data = json.loads(serialized_checkpoint)
            serialization_type = stored_data['type']
            checkpoint_bytes = bytes.fromhex(stored_data['data'])
            
            checkpoint = self.serde.loads_typed((serialization_type, checkpoint_bytes))
            
            # Apply filter if specified
            if filter and not self._matches_filter(checkpoint, filter):
                continue
            
            yield CheckpointTuple(
                config=config or RunnableConfig(),
                checkpoint=checkpoint,
                metadata={},
                parent_config=None,
                pending_writes=None,
            )
            
            # Apply limit
            if limit is not None:
                limit -= 1
                if limit <= 0:
                    break

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str | None = None,
    ) -> None:
        """Store intermediate writes for a task.
        
        Args:
            config: Runnable configuration containing thread_id
            writes: List of (channel, value, version) tuples
            task_id: Task identifier
            task_path: Optional task path (not used in this implementation)
        """
        thread_id = _get_thread_id(config)
        
        # Store writes in a separate key with TTL
        writes_key = f"writes:{thread_id}:{task_id}"
        # Convert tuples to lists for JSON serialization
        writes_as_lists = [[str(ch), val] for ch, val in writes]
        serialized_writes = json.dumps(writes_as_lists)
        
        await self._retry_redis_operation(
            lambda: self._redis_client.set(writes_key, serialized_writes, ex=self._ttl_seconds)
        )

    async def adelete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes for a thread.
        
        Args:
            thread_id: Thread identifier to delete
        """
        # Delete all checkpoint keys for this thread
        checkpoint_pattern = f"checkpoint:{thread_id}:*"
        async for key in self._scan_keys(checkpoint_pattern):
            await self._redis_client.delete(key)
        
        # Delete all write keys for this thread
        writes_pattern = f"writes:{thread_id}:*"
        async for key in self._scan_keys(writes_pattern):
            await self._redis_client.delete(key)
        
        # Delete the latest index
        latest_key = f"checkpoint:{thread_id}:latest"
        await self._redis_client.delete(latest_key)

    async def _store_checkpoint_with_ttl(self, key: str, value: str) -> None:
        """Store checkpoint with TTL using Redis SET command."""
        await self._redis_client.set(key, value, ex=self._ttl_seconds)

    async def _retry_redis_operation(self, operation) -> None:
        """Execute Redis operation with retry logic.
        
        Args:
            operation: Async callable that performs the Redis operation
            
        Raises:
            CheckpointWriteError: If operation fails after 3 retries
        """
        delays = [0.001, 0.002, 0.004]  # 1ms, 2ms, 4ms exponential backoff
        last_exception = None
        
        for delay in delays:
            try:
                await operation()
                return
            except (aioredis.ConnectionError, aioredis.TimeoutError) as e:
                last_exception = e
                await asyncio.sleep(delay)
                continue
            except (aioredis.RedisError, ValueError) as e:
                # For other exceptions, raise immediately
                raise CheckpointWriteError(f"Redis operation failed: {e}", e)
        
        # All retries failed
        raise CheckpointWriteError(
            "Redis operation failed after 3 retries", last_exception
        )

    async def _scan_keys(self, pattern: str) -> AsyncIterator[str]:
        """Lazy key scanner using Redis SCAN.
        
        Args:
            pattern: Redis key pattern to scan
            
        Yields:
            Matching keys
        """
        cursor = 0
        while True:
            cursor, keys = await self._redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            for key in keys:
                # Skip 'latest' keys as they are handled separately
                key_str = key.decode() if isinstance(key, bytes) else key
                if not key_str.endswith(":latest"):
                    yield key_str
            if cursor == 0:
                break

    def _matches_filter(self, checkpoint: Checkpoint, filter: dict) -> bool:
        """Check if checkpoint matches filter criteria.
        
        Args:
            checkpoint: Checkpoint to filter
            filter: Filter criteria
            
        Returns:
            True if checkpoint matches filter
        """
        # Simple implementation - can be enhanced with more complex filtering
        if "ts" in filter:
            checkpoint_ts = checkpoint.get("ts")
            if checkpoint_ts and checkpoint_ts < filter["ts"]:
                return False
        return True