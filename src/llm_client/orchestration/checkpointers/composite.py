"""Composite Redis+PostgreSQL checkpointer for ADR-010."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any, Optional, Callable

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
    SerializerProtocol,
)

from .errors import (
    CheckpointError,
    RedisCheckpointWriteError,
    PostgresCheckpointWriteError,
)
from .metrics import CheckpointMetrics, NullCheckpointMetrics

logger = logging.getLogger(__name__)


class RedisPostgresCheckpointer(BaseCheckpointSaver):
    """Composite checkpointer that writes to Redis (sync) and PostgreSQL (async buffer).
    
    Implements LangGraph's BaseCheckpointSaver interface, delegating to:
    - RedisCheckpointer for synchronous writes with TTL (fast read)
    - PostgresCheckpointer for asynchronous batched writes (durable storage)
    
    The composite provides read-from-Redis, fallback-to-PostgreSQL behavior.
    """
    
    def __init__(
        self,
        redis_checkpointer: BaseCheckpointSaver,
        postgres_checkpointer: BaseCheckpointSaver,
        *,
        metrics: Optional[CheckpointMetrics] = None,
        operational_writer: Optional[Any] = None,
        on_total_failure: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Initialize composite checkpointer.
        
        Args:
            redis_checkpointer: Synchronous Redis checkpointer
            postgres_checkpointer: Asynchronous PostgreSQL checkpointer
            metrics: Optional metrics collector (default: NullCheckpointMetrics)
            operational_writer: Optional operational writer for logging events
            on_total_failure: Optional callback for when both layers fail
        """
        super().__init__()
        self._redis = redis_checkpointer
        self._postgres = postgres_checkpointer
        self._metrics = metrics or NullCheckpointMetrics()
        self._operational_writer = operational_writer
        self._on_total_failure = on_total_failure
    
    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float] | None = None,
    ) -> RunnableConfig:
        """Store a checkpoint in both Redis (sync) and PostgreSQL (async buffer).
        
        Args:
            config: Runnable configuration containing thread_id
            checkpoint: Checkpoint data to store
            metadata: Checkpoint metadata
            new_versions: Optional channel version updates
            
        Returns:
            Updated config (pass-through)
            
        Raises:
            CheckpointError: If both layers fail to store the checkpoint
        """
        redis_success = False
        pg_success = False
        
        # Start Redis write (synchronous, fast)
        redis_start = time.perf_counter()
        try:
            await self._redis.aput(config, checkpoint, metadata, new_versions)
            redis_latency = (time.perf_counter() - redis_start) * 1000
            self._metrics.record_redis_write_latency(redis_latency)
            redis_success = True
        except Exception as exc:
            redis_latency = (time.perf_counter() - redis_start) * 1000
            self._metrics.record_redis_write_latency(redis_latency)
            self._metrics.increment_redis_error()
            
            # Log Redis failure to operational stream
            await self._emit_operational({
                "event": "checkpoint_redis_write_failed",
                "thread_id": config.get("configurable", {}).get("thread_id", "default"),
                "error": str(exc),
                "fallback": "postgres_only",
            })
            
            logger.warning("Redis checkpoint write failed, falling back to PostgreSQL: %s", exc)
        
        # PostgreSQL write (asynchronous buffer)
        pg_start = time.perf_counter()
        try:
            await self._postgres.aput(config, checkpoint, metadata, new_versions)
            pg_latency = (time.perf_counter() - pg_start) * 1000
            self._metrics.record_pg_buffer_latency(pg_latency)
            pg_success = True
        except Exception as exc:
            pg_latency = (time.perf_counter() - pg_start) * 1000
            self._metrics.record_pg_buffer_latency(pg_latency)
            self._metrics.increment_pg_error()
            
            logger.warning("PostgreSQL checkpoint write failed: %s", exc)
        
        # Check if both failed
        if not redis_success and not pg_success:
            # Both failed
            self._metrics.increment_both_failed()
            await self._emit_operational({
                "event": "checkpoint_both_write_failed",
                "thread_id": config.get("configurable", {}).get("thread_id", "default"),
                "error": "Both Redis and PostgreSQL checkpoint writes failed",
            })
            
            # Call the failure callback if provided
            if self._on_total_failure:
                thread_id = config.get("configurable", {}).get("thread_id", "default")
                self._on_total_failure(thread_id, "system_error")
            
            raise CheckpointError(
                "Both Redis and PostgreSQL checkpoint writes failed. "
                f"Redis error: {redis_latency if 'redis_latency' in locals() else 'unknown'}, "
                f"PostgreSQL error: {pg_latency if 'pg_latency' in locals() else 'unknown'}"
            )
        
        return config
    
    async def aget(
        self,
        config: RunnableConfig,
    ) -> Checkpoint | None:
        """Get the latest checkpoint, reading from Redis first, then PostgreSQL.
        
        Args:
            config: Runnable configuration containing thread_id
            
        Returns:
            Checkpoint data or None if not found in either layer
        """
        # Try Redis first (fast)
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        
        try:
            checkpoint = await self._redis.aget(config)
            if checkpoint is not None:
                self._metrics.increment_redis_hit()
                logger.debug("Redis read hit for thread %s", thread_id)
                return checkpoint
        except Exception as exc:
            logger.warning("Redis read failed, trying PostgreSQL: %s", exc)
            self._metrics.increment_redis_error()
        
        # Fallback to PostgreSQL
        try:
            checkpoint = await self._postgres.aget(config)
            if checkpoint is not None:
                self._metrics.increment_pg_fallback()
                logger.debug("PostgreSQL read fallback for thread %s", thread_id)
            return checkpoint
        except Exception as exc:
            logger.warning("PostgreSQL read failed: %s", exc)
            self._metrics.increment_pg_error()
            return None
    
    async def aget_tuple(
        self,
        config: RunnableConfig,
    ) -> CheckpointTuple | None:
        """Get the latest checkpoint tuple, reading from Redis first, then PostgreSQL.
        
        Args:
            config: Runnable configuration containing thread_id
            
        Returns:
            CheckpointTuple or None if not found in either layer
        """
        # Try Redis first
        try:
            checkpoint_tuple = await self._redis.aget_tuple(config)
            if checkpoint_tuple is not None:
                self._metrics.increment_redis_hit()
                return checkpoint_tuple
        except Exception as exc:
            logger.warning("Redis read failed, trying PostgreSQL: %s", exc)
            self._metrics.increment_redis_error()
        
        # Fallback to PostgreSQL
        try:
            checkpoint_tuple = await self._postgres.aget_tuple(config)
            if checkpoint_tuple is not None:
                self._metrics.increment_pg_fallback()
            return checkpoint_tuple
        except Exception as exc:
            logger.warning("PostgreSQL read failed: %s", exc)
            self._metrics.increment_pg_error()
            return None
    
    async def alist(
        self,
        config: RunnableConfig | None = None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints from both layers, merged and sorted.
        
        Args:
            config: Optional runnable configuration to filter by thread_id
            filter: Optional filter criteria
            before: Optional checkpoint_id to list before
            limit: Optional maximum number of checkpoints to return
            
        Yields:
            CheckpointTuple objects, sorted by created_at (newest first)
        """
        # Get checkpoints from both layers
        redis_checkpoints = []
        postgres_checkpoints = []
        
        # Collect Redis checkpoints
        if config is not None:
            try:
                async for checkpoint in self._redis.alist(config, filter=filter, before=before, limit=limit):
                    redis_checkpoints.append(checkpoint)
            except Exception as exc:
                logger.warning("Redis list failed: %s", exc)
                self._metrics.increment_redis_error()
        
        # Collect PostgreSQL checkpoints
        if config is not None:
            try:
                async for checkpoint in self._postgres.alist(config, filter=filter, before=before, limit=limit):
                    postgres_checkpoints.append(checkpoint)
            except Exception as exc:
                logger.warning("PostgreSQL list failed: %s", exc)
                self._metrics.increment_pg_error()
        
        # Merge and deduplicate by checkpoint_id
        seen_ids = set()
        merged = []
        
        # Add Redis checkpoints first (they're newer)
        for checkpoint in redis_checkpoints:
            if checkpoint.checkpoint.get("id") not in seen_ids:
                seen_ids.add(checkpoint.checkpoint.get("id"))
                merged.append(checkpoint)
        
        # Add PostgreSQL checkpoints, avoiding duplicates
        for checkpoint in postgres_checkpoints:
            if checkpoint.checkpoint.get("id") not in seen_ids:
                seen_ids.add(checkpoint.checkpoint.get("id"))
                merged.append(checkpoint)
        
        # Sort by created_at (newest first)
        merged.sort(
            key=lambda cp: (
                cp.checkpoint.get("ts", ""),
                cp.checkpoint.get("id", ""),
            ),
            reverse=True
        )
        
        # Apply limit
        if limit is not None:
            merged = merged[:limit]
        
        # Yield results
        for checkpoint in merged:
            yield checkpoint
    
    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str | None = None,
    ) -> None:
        """Store intermediate writes in both layers.
        
        Args:
            config: Runnable configuration containing thread_id
            writes: List of (channel, value) tuples
            task_id: Task identifier
            task_path: Optional task path (not used in this implementation)
        """
        # Delegate to both layers
        try:
            await self._redis.aput_writes(config, writes, task_id, task_path)
        except Exception as exc:
            logger.warning("Redis writes failed: %s", exc)
            self._metrics.increment_redis_error()
        
        try:
            await self._postgres.aput_writes(config, writes, task_id, task_path)
        except Exception as exc:
            logger.warning("PostgreSQL writes failed: %s", exc)
            self._metrics.increment_pg_error()
    
    async def adelete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes for a thread from both layers.
        
        Args:
            thread_id: Thread identifier to delete
        """
        # Delegate to both layers
        try:
            await self._redis.adelete_thread(thread_id)
        except Exception as exc:
            logger.warning("Redis thread deletion failed: %s", exc)
            self._metrics.increment_redis_error()
        
        try:
            await self._postgres.adelete_thread(thread_id)
        except Exception as exc:
            logger.warning("PostgreSQL thread deletion failed: %s", exc)
            self._metrics.increment_pg_error()
    
    async def _emit_operational(self, event: dict[str, Any]) -> None:
        """Emit an event to the operational writer if available.
        
        Args:
            event: Event dictionary to emit
        """
        if self._operational_writer is not None:
            try:
                await self._operational_writer.write(event)
            except Exception as exc:
                logger.warning("Failed to write operational event: %s", exc)
        else:
            # Fallback to logging
            logger.info("Operational event: %s", event)