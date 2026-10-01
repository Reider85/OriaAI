"""Composite Redis+PostgreSQL checkpointer for ADR-010."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import redis.asyncio as aioredis
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
)

from .errors import CheckpointError
from .metrics import CheckpointMetrics, NullCheckpointMetrics

logger = logging.getLogger(__name__)

#: Seconds of wall clock a single ``recover()`` pass may spend before it gives
#: up on the remaining threads. 30 s is the B-5 startup budget: a partial
#: recovery beats a cold start, so exceeding it degrades to "PG snapshot only"
#: for the threads that were not reached.
RECOVERY_TIMEOUT_SECONDS = 30.0

#: Look-back window for the PG-seeded thread list. Matches the Redis checkpoint
#: TTL (24 h) — an older thread has no Redis delta left to replay.
RECOVERY_WINDOW_SECONDS = 86400

#: Largest checkpoint ``ts`` difference treated as "same instant" for conflict
#: resolution. LangGraph writes ``ts`` with microsecond precision, so equal
#: timestamps mean the same node transition; the slack only absorbs clock skew
#: between the layer that wrote the checkpoint and the one comparing it.
_RECOVERY_TIMESTAMP_SLACK_SECONDS = 0.001


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
        metrics: CheckpointMetrics | None = None,
        operational_writer: Any | None = None,
        on_total_failure: Callable[[str, str], None] | None = None,
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
            await self._redis.aput(config, checkpoint, metadata, new_versions or {})
            redis_latency = (time.perf_counter() - redis_start) * 1000
            self._metrics.record_redis_write_latency(redis_latency)
            redis_success = True
        except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — never break /metrics on one bad collector
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
            await self._postgres.aput(config, checkpoint, metadata, new_versions or {})
            pg_latency = (time.perf_counter() - pg_start) * 1000
            self._metrics.record_pg_buffer_latency(pg_latency)
            pg_success = True
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — never break /metrics on one bad collector
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
        except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — degrade to PostgreSQL on any Redis failure
            logger.warning("Redis read failed, trying PostgreSQL: %s", exc)
            self._metrics.increment_redis_error()
        
        # Fallback to PostgreSQL
        try:
            checkpoint = await self._postgres.aget(config)
            if checkpoint is not None:
                self._metrics.increment_pg_fallback()
                logger.debug("PostgreSQL read fallback for thread %s", thread_id)
            return checkpoint
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — degrade to error logging if PostgreSQL fails
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
        except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — degrade to PostgreSQL on any Redis failure
            logger.warning("Redis read failed, trying PostgreSQL: %s", exc)
            self._metrics.increment_redis_error()
        
        # Fallback to PostgreSQL
        try:
            checkpoint_tuple = await self._postgres.aget_tuple(config)
            if checkpoint_tuple is not None:
                self._metrics.increment_pg_fallback()
            return checkpoint_tuple
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — degrade to error logging if PostgreSQL fails
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
            except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — degrade to PostgreSQL on any Redis failure
                logger.warning("Redis list failed: %s", exc)
                self._metrics.increment_redis_error()
        
        # Collect PostgreSQL checkpoints
        if config is not None:
            try:
                async for checkpoint in self._postgres.alist(config, filter=filter, before=before, limit=limit):
                    postgres_checkpoints.append(checkpoint)
            except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — degrade to empty list if PostgreSQL fails
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
            await self._redis.aput_writes(config, writes, task_id, task_path or "")
        except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — continue to PostgreSQL if Redis fails
            logger.warning("Redis writes failed: %s", exc)
            self._metrics.increment_redis_error()
        
        try:
            await self._postgres.aput_writes(config, writes, task_id, task_path or "")
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — log but don't fail if PostgreSQL fails
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
        except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — continue to PostgreSQL if Redis fails
            logger.warning("Redis thread deletion failed: %s", exc)
            self._metrics.increment_redis_error()
        
        try:
            await self._postgres.adelete_thread(thread_id)
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — log but don't fail if PostgreSQL fails
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
            except Exception as exc:  # noqa: BLE001 — never break checkpointing on write failure
                logger.warning("Failed to write operational event: %s", exc)
        else:
            # Fallback to logging
            logger.info("Operational event: %s", event)

    # ------------------------------------------------------------------
    # B-5 recovery protocol
    # ------------------------------------------------------------------

    async def recover(
        self,
        *,
        timeout_seconds: float = RECOVERY_TIMEOUT_SECONDS,
        window_seconds: int = RECOVERY_WINDOW_SECONDS,
    ) -> dict[str, int]:
        """Restore state after a restart: PostgreSQL snapshot, then Redis delta.

        PostgreSQL holds the durable snapshot, but it only learns about a
        checkpoint once the batched flusher runs (every ``flush_interval_seconds``,
        B-4). Anything written to Redis in the meantime is newer than the last
        snapshot, so recovery replays that delta into the PostgreSQL buffer and
        lets the next flush persist it. This is a feedback loop between two
        layers, not a single source of truth (TRIZ principle 23).

        Per thread, in priority order:

        * Redis is newer  → replay the Redis checkpoint into PostgreSQL
          (``redis_delta_replayed``).
        * PostgreSQL is newer → keep it; Redis is stale
          (``pg_checkpoints_recovered``).
        * Same instant, different content → PostgreSQL wins and the Redis copy
          is overwritten from it (``conflicts_resolved``), because the durable
          layer is the more trustworthy of two writes to the same transition.
        * Redis key gone (TTL expired) or Redis unreachable → PostgreSQL-only
          recovery. Losing the last <=5 s of checkpoints is ADR-010's accepted
          risk, not an error.

        A thread whose state fails validation is recorded as needing human review
        and left untouched — recovery never overwrites state it cannot parse
        (forensics via ADR-014).

        Args:
            timeout_seconds: Wall-clock budget for the pass. On expiry the
                remaining threads are skipped and the stats returned so far are
                reported with a warning (a partial recovery still beats a cold
                start).
            window_seconds: PG look-back window for which threads to consider.
                Defaults to the Redis TTL; older threads have no delta left.

        Returns:
            Counters describing the run: ``pg_checkpoints_recovered``,
            ``redis_delta_replayed``, ``conflicts_resolved``,
            ``corrupted_states`` and ``threads_skipped`` (past the timeout).
        """
        started = time.perf_counter()
        deadline = started + timeout_seconds

        stats = {
            "pg_checkpoints_recovered": 0,
            "redis_delta_replayed": 0,
            "conflicts_resolved": 0,
            "corrupted_states": 0,
            "threads_skipped": 0,
        }

        thread_ids, redis_reachable = await self._collect_recovery_threads(window_seconds)
        self._metrics.set_recovery_threads(len(thread_ids))

        for thread_id in thread_ids:
            if time.perf_counter() >= deadline:
                stats["threads_skipped"] = len(thread_ids) - (
                    stats["pg_checkpoints_recovered"]
                    + stats["redis_delta_replayed"]
                    + stats["conflicts_resolved"]
                    + stats["corrupted_states"]
                )
                self._metrics.increment_recovery_timeout()
                logger.warning(
                    '{"event": "checkpoint_recovery_timeout", "timeout_seconds": %.1f, '
                    '"threads_skipped": %d, "partial": true}',
                    timeout_seconds,
                    stats["threads_skipped"],
                )
                break

            await self._recover_thread(thread_id, redis_reachable, stats)

        duration_ms = (time.perf_counter() - started) * 1000
        self._metrics.record_recovery_duration(duration_ms)

        logger.info(
            '{"event": "checkpoint_recovery_done", "pg_checkpoints_recovered": %d, '
            '"redis_delta_replayed": %d, "conflicts_resolved": %d, '
            '"corrupted_states": %d, "threads_skipped": %d, "duration_ms": %.1f}',
            stats["pg_checkpoints_recovered"],
            stats["redis_delta_replayed"],
            stats["conflicts_resolved"],
            stats["corrupted_states"],
            stats["threads_skipped"],
            duration_ms,
        )
        return stats

    async def _collect_recovery_threads(self, window_seconds: int) -> tuple[list[str], bool]:
        """Return the threads to recover and whether Redis was reachable.

        PostgreSQL is the seed (durable) and Redis contributes threads it alone
        knows about (written since the last flush). A Redis outage degrades to
        PG-only recovery rather than failing the pass, so reachability is
        reported alongside the thread list instead of raised.
        """
        thread_ids: list[str] = []
        redis_reachable = True

        try:
            pg_threads = await self._postgres.list_active_thread_ids(window_seconds)  # type: ignore[attr-defined]
            thread_ids.extend(pg_threads)
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — Redis still has recent writes, continue
            # Without the durable layer there is no snapshot to restore from;
            # Redis alone still holds the last writes, so try it and log.
            logger.warning(
                '{"event": "checkpoint_recovery_pg_unavailable", "error": %r}', exc
            )

        try:
            redis_threads = await self._redis.list_all_thread_ids()  # type: ignore[attr-defined]
            thread_ids.extend(redis_threads)
        except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — Redis unavailable, continue with empty list
            logger.warning(
                '{"event": "checkpoint_recovery_redis_unavailable", "error": %r}', exc
            )
            redis_reachable = False

        # Deduplicate while preserving order; the PG entries come first.
        return list(dict.fromkeys(thread_ids)), redis_reachable

    async def _recover_thread(
        self,
        thread_id: str,
        redis_reachable: bool,
        stats: dict[str, int],
    ) -> None:
        """Reconcile one thread across both layers and update *stats* in place.

        A layer that is merely unreachable is not an error for this thread: the
        pass degrades to whatever the other layer holds and keeps going. Only a
        thread that ends up with unusable state is recorded as needing review.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        try:
            pg_tuple = await self._postgres.aget_tuple(config)
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — PG down, Redis still has recent writes
            # Scenario 3: PG is down/restarting. Redis still has the recent
            # writes, so report the thread as unreconciled and move on — the
            # snapshot arrives on the next restart.
            logger.warning(
                '{"event": "checkpoint_recovery_pg_read_failed", "thread_id": "%s", '
                '"error": %r}',
                thread_id,
                exc,
            )
            pg_tuple = None

        redis_tuple: CheckpointTuple | None = None
        if redis_reachable:
            try:
                redis_tuple = await self._redis.aget_tuple(config)
            except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — Redis read failed, continue with None
                logger.warning(
                    '{"event": "checkpoint_recovery_redis_read_failed", "thread_id": "%s", '
                    '"error": %r}',
                    thread_id,
                    exc,
                )

        if redis_tuple is None:
            # Nothing newer in the hot layer (or Redis is down) — PG wins by default.
            if pg_tuple is not None:
                stats["pg_checkpoints_recovered"] += 1
                self._metrics.increment_recovery_pg_recovered()
                await self._log_recovery(thread_id, pg_tuple, None, delta_replayed=False)
            return

        if pg_tuple is None:
            # PG has not seen this thread at all (written since the last flush):
            # replay the whole checkpoint, not just a delta. When PG is merely
            # unreachable the replay cannot land, so the thread is left for the
            # next pass rather than counted as replayed.
            if not self._replayable(thread_id, redis_tuple, stats):
                return
            if not await self._replay_to_postgres(thread_id, redis_tuple):
                stats["threads_skipped"] += 1
                return
            stats["redis_delta_replayed"] += 1
            self._metrics.increment_recovery_delta_replayed()
            await self._log_recovery(thread_id, None, redis_tuple, delta_replayed=True)
            await self._validate_recovered_thread(thread_id, stats)
            return

        comparison = _compare_timestamps(
            redis_tuple.checkpoint, pg_tuple.checkpoint
        )

        if comparison > 0:
            # Redis strictly newer — replay the delta.
            if not self._replayable(thread_id, redis_tuple, stats):
                return
            if not await self._replay_to_postgres(thread_id, redis_tuple):
                stats["threads_skipped"] += 1
                return
            stats["redis_delta_replayed"] += 1
            self._metrics.increment_recovery_delta_replayed()
            await self._log_recovery(thread_id, pg_tuple, redis_tuple, delta_replayed=True)
            await self._validate_recovered_thread(thread_id, stats)
            return

        if comparison < 0:
            # PG strictly newer — Redis is stale; PG snapshot stands.
            stats["pg_checkpoints_recovered"] += 1
            self._metrics.increment_recovery_pg_recovered()
            await self._log_recovery(thread_id, pg_tuple, redis_tuple, delta_replayed=False)
            return

        # Same instant. Identical content is the common case (both layers
        # already hold the same node transition) and needs no action; differing
        # content is the rare genuine conflict, resolved in favour of PG.
        if redis_tuple.checkpoint != pg_tuple.checkpoint:
            stats["conflicts_resolved"] += 1
            self._metrics.increment_recovery_conflict()
            await self._emit_operational({
                "event": "checkpoint_conflict",
                "thread_id": thread_id,
                "winner": "pg",
                "reason": "content_diff",
                "pg_checkpoint_id": pg_tuple.checkpoint.get("id"),
                "redis_checkpoint_id": redis_tuple.checkpoint.get("id"),
            })
            try:
                await self._redis.aput(
                    config, pg_tuple.checkpoint, pg_tuple.metadata, {}
                )
            except (aioredis.RedisError, Exception) as exc:  # noqa: BLE001 — Redis write failed, continue with PG state
                logger.warning(
                    '{"event": "checkpoint_conflict_rewrite_failed", "thread_id": "%s", '
                    '"error": %r}',
                    thread_id,
                    exc,
                )
        else:
            stats["pg_checkpoints_recovered"] += 1
            self._metrics.increment_recovery_pg_recovered()

        await self._log_recovery(
            thread_id,
            pg_tuple,
            redis_tuple,
            delta_replayed=comparison > 0,
        )

    async def _replay_to_postgres(
        self,
        thread_id: str,
        redis_tuple: CheckpointTuple,
    ) -> bool:
        """Push a recovered Redis checkpoint into the PostgreSQL buffer.

        The write is buffered, not synchronous — it lands in ``agent_checkpoints``
        on the next background flush. ``recover()`` runs before the flusher
        accepts traffic, so the delta is durable before the first request.

        Returns:
            True if the delta was buffered, False if PostgreSQL rejected it (the
            caller then reports the thread as unreconciled instead of claiming a
            replay that never happened).
        """
        try:
            await self._postgres.replay_checkpoint(  # type: ignore[attr-defined]
                thread_id, redis_tuple.checkpoint, redis_tuple.metadata
            )
        except (asyncpg.PostgresError, Exception) as exc:  # noqa: BLE001 — replay failed, but Redis still has latest state
            logger.warning(
                '{"event": "checkpoint_recovery_replay_failed", "thread_id": "%s", '
                '"error": %r}',
                thread_id,
                exc,
            )
            return False
        return True

    def _replayable(
        self,
        thread_id: str,
        redis_tuple: CheckpointTuple,
        stats: dict[str, int],
    ) -> bool:
        """Gate a replay on the source checkpoint being well-formed.

        Checked *before* the write: promoting an unreadable checkpoint into the
        durable layer would overwrite a good snapshot with damage, and ADR-010
        forbids auto-repairing state recovery cannot trust. A thread that fails
        here is recorded for human review and left exactly as it was.
        """
        if _is_valid_checkpoint(redis_tuple.checkpoint):
            return True
        self._mark_needs_review(thread_id, stats, "corrupted_source_checkpoint")
        return False

    async def _validate_recovered_thread(
        self,
        thread_id: str,
        stats: dict[str, int],
    ) -> None:
        """Confirm a replayed thread reads back cleanly, or flag it for review.

        Reads through the composite, which is the path the graph itself takes,
        so this asserts what a resumed run will actually see rather than what a
        single layer happens to hold.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        try:
            recovered = await self.aget(config)
        except Exception as exc:  # noqa: BLE001 — mark for review but don't crash recovery
            self._mark_needs_review(thread_id, stats, f"read_failed: {exc}")
            return

        if recovered is None or not _is_valid_checkpoint(recovered):
            self._mark_needs_review(thread_id, stats, "corrupted_state")

    def _mark_needs_review(
        self,
        thread_id: str,
        stats: dict[str, int],
        reason: str,
    ) -> None:
        """Record a thread as unrecoverable and emit a forensic event (ADR-014)."""
        stats["corrupted_states"] += 1
        self._metrics.increment_recovery_corrupted()
        logger.error(
            '{"event": "checkpoint_recovery_needs_human_review", "thread_id": "%s", '
            '"reason": "%s"}',
            thread_id,
            reason,
        )
        # Best-effort: the forensic writer may itself be unavailable at startup.
        asyncio.create_task(self._emit_operational({
            "event": "checkpoint_recovery_needs_human_review",
            "thread_id": thread_id,
            "reason": reason,
        }))

    async def _log_recovery(
        self,
        thread_id: str,
        pg_tuple: CheckpointTuple | None,
        redis_tuple: CheckpointTuple | None,
        *,
        delta_replayed: bool,
    ) -> None:
        """Emit the per-thread ``checkpoint_recovery`` event."""
        await self._emit_operational({
            "event": "checkpoint_recovery",
            "thread_id": thread_id,
            "pg_checkpoint_id": (pg_tuple.checkpoint.get("id") if pg_tuple else None),
            "redis_checkpoint_id": (redis_tuple.checkpoint.get("id") if redis_tuple else None),
            "delta_replayed": delta_replayed,
        })


# ----------------------------------------------------------------------
# Module helpers
# ----------------------------------------------------------------------


def _parse_ts(value: Any) -> Any:
    """Parse a LangGraph ``ts`` field into an aware datetime, or None if absent.

    LangGraph writes ``ts`` as an ISO-8601 string with a ``Z``/offset suffix.
    An unparseable or missing value yields ``None`` so the caller can treat the
    checkpoint as having no usable ordering rather than guessing.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _compare_timestamps(redis_checkpoint: Checkpoint, pg_checkpoint: Checkpoint) -> int:
    """Compare two checkpoints' ``ts``: +1 if Redis is newer, -1 if PG, 0 if equal.

    A checkpoint with no parseable timestamp cannot be ordered, so it is treated
    as equal and routed to the conflict path — which prefers the durable layer.
    """
    redis_ts = _parse_ts(redis_checkpoint.get("ts"))
    pg_ts = _parse_ts(pg_checkpoint.get("ts"))

    if redis_ts is None or pg_ts is None:
        return 0

    slack = timedelta(seconds=_RECOVERY_TIMESTAMP_SLACK_SECONDS)
    if redis_ts - pg_ts > slack:
        return 1
    if pg_ts - redis_ts > slack:
        return -1
    return 0


def _is_valid_checkpoint(checkpoint: Checkpoint) -> bool:
    """Shape check for a recovered checkpoint.

    Deliberately minimal: it confirms the fields recovery and LangGraph's resume
    path depend on are present and well-typed, without attempting to interpret
    the channel values. A stricter check risks rejecting a legitimate state and
    silently discarding recoverable work.
    """
    if not isinstance(checkpoint, dict):
        return False
    if not checkpoint.get("id"):
        return False
    if not isinstance(checkpoint.get("channel_values"), (dict, list)):
        return False
    return isinstance(checkpoint.get("channel_versions"), dict)
