"""PostgreSQL-based asynchronous batched checkpoint saver for LangGraph (ADR-010).

Implements LangGraph's ``BaseCheckpointSaver`` interface as the *cold* half of
ADR-010: ``aput`` never touches PostgreSQL, it only appends to an in-memory
buffer. Durable writes happen in ``_flush()``, which upserts whole batches in a
single round-trip (TRIZ principle 19, periodic action).

The companion :class:`~llm_client.orchestration.checkpointers.redis_checkpointer.RedisCheckpointer`
(B-1) is the *hot* synchronous read/write path; this class only backs it up so
that PostgreSQL sees ~1 batch per ``flush_interval_seconds`` instead of one
INSERT per graph node.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any, NamedTuple

import asyncpg
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
    SerializerProtocol,
)

from .errors import CheckpointWriteError

logger = logging.getLogger(__name__)

__all__ = ["PostgresCheckpointer"]

_CHECKPOINT_COLUMNS = "thread_id, checkpoint_id, parent_id, state, metadata, created_at"

_FLUSH_PREAMBLE = (
    f"INSERT INTO agent_checkpoints ({_CHECKPOINT_COLUMNS}) VALUES "
)

# Single-row upsert. Used for the common case of one buffered checkpoint so the
# statement text stays constant and can be cached by the PG planner.
_FLUSH_ONE_SQL = (
    _FLUSH_PREAMBLE
    + "($1, $2, $3, $4, $5, $6) "
    "ON CONFLICT (thread_id, checkpoint_id) DO UPDATE SET "
    "state = EXCLUDED.state, "
    "metadata = EXCLUDED.metadata, "
    "created_at = EXCLUDED.created_at"
)

_SELECT_LATEST_SQL = (
    f"SELECT {_CHECKPOINT_COLUMNS} FROM agent_checkpoints "
    "WHERE thread_id = $1 ORDER BY created_at DESC, checkpoint_id DESC LIMIT 1"
)

_SELECT_LIST_SQL = (
    f"SELECT {_CHECKPOINT_COLUMNS} FROM agent_checkpoints "
    "WHERE thread_id = $1 AND created_at < $2 "
    "ORDER BY created_at DESC, checkpoint_id DESC LIMIT $3"
)

_DELETE_THREAD_SQL = "DELETE FROM agent_checkpoints WHERE thread_id = $1"

# Placeholder period while a full buffer waits for the flusher to drain it.
_BACKPRESSURE_POLL_SECONDS = 0.1


class _PendingCheckpoint(NamedTuple):
    """A buffered checkpoint plus everything ``_flush`` needs to persist it."""

    key: str
    thread_id: uuid.UUID
    checkpoint_id: uuid.UUID
    parent_id: uuid.UUID | None
    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    created_at: datetime


class PostgresCheckpointer(BaseCheckpointSaver):
    """Asynchronous batched PostgreSQL checkpoint saver (ADR-010 async layer).

    Unlike :class:`RedisCheckpointer` this class never writes to storage on the
    hot path. ``aput`` is an in-memory dict append (target <1 ms); a background
    flusher (B-4, :meth:`_flush_loop`) drains the buffer in upsert batches.

    Args:
        pg_pool: Existing ``asyncpg`` connection pool. Reused as-is — this class
            never creates or closes connections (ADR-005: PostgreSQL is the
            primary datastore, not a checkpointer-owned resource).
        flush_interval_seconds: Max delay between flushes (default: 5).
        flush_batch_size: Max rows per batched INSERT (default: 50).
        serde: Optional serializer override (default: LangGraph ``JsonPlusSerializer``).
        max_buffer_multiplier: Buffer capacity as a multiple of
            ``flush_batch_size`` (default: 10 → 500 checkpoints), the point at
            which ``aput`` applies backpressure.
        backpressure_timeout_seconds: How long a full buffer may block ``aput``
            before it logs an error and proceeds anyway (default: 30).
    """

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        flush_interval_seconds: int = 5,
        flush_batch_size: int = 50,
        serde: SerializerProtocol | None = None,
        *,
        max_buffer_multiplier: int = 10,
        backpressure_timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(serde=serde)
        if flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds must be > 0")
        if flush_batch_size <= 0:
            raise ValueError("flush_batch_size must be > 0")
        if max_buffer_multiplier <= 1:
            raise ValueError("max_buffer_multiplier must be > 1")

        self._pg_pool = pg_pool
        # Public: B-4's flusher reads these to drive the periodic loop.
        self.flush_interval_seconds = flush_interval_seconds
        self.flush_batch_size = flush_batch_size
        self._max_buffer_size = flush_batch_size * max_buffer_multiplier
        self._backpressure_timeout = backpressure_timeout_seconds

        # Pending writes only. Read path is served by RedisCheckpointer (B-1).
        self._buffer: dict[str, _PendingCheckpoint] = {}
        self._writes_buffer: dict[tuple[str, str], list[tuple[str, Any]]] = {}
        self._buffer_not_full = asyncio.Condition()
        self._panic_mode = False
        # B-4 flips this in stop_flush_loop() to break the loop.
        self._stopping = False
        # Guards _flush() against concurrent time-based and size-based triggers.
        self._flush_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # BaseCheckpointSaver interface
    # ------------------------------------------------------------------

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float] | None = None,
    ) -> RunnableConfig:
        """Buffer a checkpoint for the next batched flush. No PG I/O happens here.

        Args:
            config: Runnable configuration containing ``thread_id``.
            checkpoint: Checkpoint data to persist.
            metadata: Checkpoint metadata.
            new_versions: Optional channel version updates (unused — LangGraph's
                own PostgreSQL saver derives versions from ``channel_versions``).

        Returns:
            The config unchanged (pass-through), per the saver contract.
        """
        thread_id = _require_thread_id(config)
        checkpoint_id = _require_checkpoint_id(checkpoint)

        await self._apply_backpressure()

        self._buffer[checkpoint_id] = _PendingCheckpoint(
            key=checkpoint_id,
            thread_id=_as_uuid(thread_id, "thread_id"),
            checkpoint_id=_as_uuid(checkpoint_id, "checkpoint_id"),
            parent_id=_as_optional_uuid(
                checkpoint.get("parent_checkpoint_id"), "parent_checkpoint_id"
            ),
            checkpoint=checkpoint,
            metadata=metadata,
            created_at=_parse_timestamp(checkpoint.get("ts")),
        )

        if len(self._buffer) >= self._max_buffer_size and not self._panic_mode:
            logger.warning(
                "checkpoint buffer full (%d/%d), entering panic mode — "
                "flushing on every aput",
                len(self._buffer),
                self._max_buffer_size,
            )
            self._panic_mode = True

        if self._panic_mode or len(self._buffer) >= self.flush_batch_size:
            # Fire-and-forget: aput stays non-blocking on the happy path. The
            # background loop (B-4) is the primary drain mechanism.
            asyncio.create_task(self._flush())

        return config

    async def aget(self, config: RunnableConfig) -> Checkpoint | None:
        """Return the latest checkpoint for a thread, buffer first, then PostgreSQL."""
        thread_id = _require_thread_id(config)

        pending = self._latest_buffered(thread_id)
        if pending is not None:
            return pending.checkpoint

        row = await self._pg_pool.fetchrow(_SELECT_LATEST_SQL, _as_uuid(thread_id, "thread_id"))
        if row is None:
            return None
        return _load_checkpoint(self.serde, row)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Return the latest checkpoint plus its metadata, buffer first."""
        thread_id = _require_thread_id(config)

        pending = self._latest_buffered(thread_id)
        if pending is not None:
            return CheckpointTuple(
                config=config,
                checkpoint=pending.checkpoint,
                metadata=pending.metadata,
                parent_config=(
                    {"configurable": {"thread_id": thread_id, "checkpoint_id": pending.parent_id}}
                    if pending.parent_id
                    else None
                ),
                pending_writes=None,
            )

        row = await self._pg_pool.fetchrow(_SELECT_LATEST_SQL, _as_uuid(thread_id, "thread_id"))
        if row is None:
            return None
        return _row_to_tuple(self.serde, row, thread_id)

    async def alist(
        self,
        config: RunnableConfig | None = None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Yield checkpoints for a thread, newest first, buffer merged over PostgreSQL.

        Buffered-but-unflushed checkpoints are yielded first so callers never
        miss a write that is still in flight. PostgreSQL results that duplicate
        an unflushed id are skipped.
        """
        if config is None:
            config = {}
        thread_id = _require_thread_id(config)
        before_ts = _before_timestamp(before)

        remaining = limit
        seen_ids: set[str] = set()

        for pending in self._buffered_for_thread(thread_id):
            if before_ts is not None and pending.created_at >= before_ts:
                continue
            if filter and not _matches_filter(pending.metadata, filter):
                continue
            seen_ids.add(str(pending.checkpoint_id))
            yield CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_id": str(pending.checkpoint_id)}},
                checkpoint=pending.checkpoint,
                metadata=pending.metadata,
                parent_config=(
                    {"configurable": {"thread_id": thread_id, "checkpoint_id": str(pending.parent_id)}}
                    if pending.parent_id
                    else None
                ),
                pending_writes=None,
            )
            if remaining is not None:
                remaining -= 1
                if remaining <= 0:
                    return

        if remaining is None or remaining > 0:
            rows = await self._pg_pool.fetch(
                _SELECT_LIST_SQL,
                _as_uuid(thread_id, "thread_id"),
                before_ts or datetime.max.replace(tzinfo=UTC),
                remaining if remaining is not None else self._max_buffer_size,
            )
            for row in rows:
                if str(row["checkpoint_id"]) in seen_ids:
                    continue
                if filter and not _matches_filter(_as_dict(row["metadata"]), filter):
                    continue
                yield _row_to_tuple(self.serde, row, thread_id)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Buffer intermediate writes for a task, separately from checkpoints.

        Pending writes are not persisted: ``agent_checkpoints`` (ADR-001) has no
        writes column and the spec forbids schema changes. They live only until
        the flush that follows the owning checkpoint, and are exposed for
        recovery tooling. RedisCheckpointer (B-1) is the durable store for
        in-flight writes.
        """
        thread_id = _require_thread_id(config)
        self._writes_buffer[(thread_id, task_id)] = list(writes)

    async def adelete_thread(self, thread_id: str) -> None:
        """Drop every checkpoint for a thread from PostgreSQL and from the buffer."""
        for key in [
            k for k, pending in self._buffer.items() if str(pending.thread_id) == str(thread_id)
        ]:
            del self._buffer[key]
        for key in [k for k in self._writes_buffer if k[0] == thread_id]:
            del self._writes_buffer[key]

        await self._pg_pool.execute(_DELETE_THREAD_SQL, _as_uuid(thread_id, "thread_id"))

    # ------------------------------------------------------------------
    # Flushing
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        """Periodic drain loop. Started by B-4 via ``start_flush_loop()``."""
        while not self._stopping:
            await asyncio.sleep(self.flush_interval_seconds)
            await self._flush()

    async def _flush(self) -> None:
        """Upsert buffered checkpoints into ``agent_checkpoints`` in batches.

        The buffer is drained completely, in chunks of ``flush_batch_size`` so no
        single statement grows unbounded. Draining fully (rather than one chunk
        per tick) is what keeps the buffer from growing at high write rates: the
        time-based loop can only fire every ``flush_interval_seconds``, so a
        partial flush would let a burst outpace the flusher.

        On failure the buffer is left untouched so the next flush retries — losing
        a pending checkpoint silently is worse than a retry.
        """
        async with self._flush_lock:
            if not self._buffer:
                return

            started = time.perf_counter()
            total = 0
            while True:
                batch = self._peek_batch()
                if not batch:
                    break
                try:
                    await self._write_batch(batch)
                except Exception as exc:
                    logger.error(
                        '{"event": "checkpoint_flush_failed", "count": %d, "error": %r}',
                        len(batch),
                        exc,
                    )
                    raise CheckpointWriteError(f"PostgreSQL flush failed: {exc}", exc) from exc

                for pending in batch:
                    del self._buffer[pending.key]
                total += len(batch)

            async with self._buffer_not_full:
                self._buffer_not_full.notify_all()

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            '{"event": "checkpoint_flush", "count": %d, "duration_ms": %.1f}',
            total,
            duration_ms,
        )
        if self._panic_mode and len(self._buffer) < self._max_buffer_size // 2:
            logger.info("checkpoint buffer drained, leaving panic mode")
            self._panic_mode = False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _peek_batch(self) -> list[_PendingCheckpoint]:
        """Return up to ``flush_batch_size`` buffered rows without removing them."""
        batch: list[_PendingCheckpoint] = []
        for pending in self._buffer.values():
            batch.append(pending)
            if len(batch) >= self.flush_batch_size:
                break
        return batch

    async def _write_batch(self, batch: list[_PendingCheckpoint]) -> None:
        """Send one batch to PostgreSQL as a single multi-row upsert."""
        if not batch:
            return
        if len(batch) == 1:
            await self._pg_pool.execute(_FLUSH_ONE_SQL, *_flush_args(self.serde, batch[0]))
            return

        placeholders = ", ".join(
            "(" + ", ".join(f"${i * 6 + j + 1}" for j in range(6)) + ")"
            for i in range(len(batch))
        )
        sql = (
            _FLUSH_PREAMBLE
            + placeholders
            + " ON CONFLICT (thread_id, checkpoint_id) DO UPDATE SET "
            "state = EXCLUDED.state, "
            "metadata = EXCLUDED.metadata, "
            "created_at = EXCLUDED.created_at"
        )
        args: list[Any] = []
        for pending in batch:
            args.extend(_flush_args(self.serde, pending))
        await self._pg_pool.execute(sql, *args)

    async def _apply_backpressure(self) -> None:
        """Block while the buffer is at capacity so it cannot grow without bound.

        A stuck PostgreSQL must not turn into unbounded memory growth, so this
        waits — but never forever. After ``backpressure_timeout_seconds`` it logs
        an error and proceeds: the checkpoint still lands in the buffer, and
        RedisCheckpointer (B-1) remains the durable hot copy.
        """
        if len(self._buffer) < self._max_buffer_size:
            return

        waited = 0.0
        while len(self._buffer) >= self._max_buffer_size:
            asyncio.create_task(self._flush())
            try:
                async with self._buffer_not_full:
                    await asyncio.wait_for(
                        self._buffer_not_full.wait(), timeout=_BACKPRESSURE_POLL_SECONDS
                    )
                waited = 0.0
                continue
            except TimeoutError:
                waited += _BACKPRESSURE_POLL_SECONDS
                logger.warning(
                    "checkpoint buffer full (%d/%d), waiting for flush: %.1fs",
                    len(self._buffer),
                    self._max_buffer_size,
                    waited,
                )
                if waited >= self._backpressure_timeout:
                    logger.error(
                        "checkpoint buffer still full after %.1fs, proceeding anyway "
                        "to avoid dropping the checkpoint",
                        waited,
                    )
                    return

    def _latest_buffered(self, thread_id: str) -> _PendingCheckpoint | None:
        """Return the most recently buffered checkpoint for a thread, if any."""
        for pending in reversed(list(self._buffer.values())):
            if str(pending.thread_id) == str(thread_id):
                return pending
        return None

    def _buffered_for_thread(self, thread_id: str) -> list[_PendingCheckpoint]:
        """Return buffered checkpoints for a thread, newest first."""
        found = [p for p in self._buffer.values() if str(p.thread_id) == str(thread_id)]
        return sorted(found, key=lambda p: (p.created_at, str(p.checkpoint_id)), reverse=True)

    @property
    def buffer_size(self) -> int:
        """Number of checkpoints awaiting a flush (metric ``checkpoint_buffer_size``)."""
        return len(self._buffer)

    @property
    def max_buffer_size(self) -> int:
        """Buffer capacity before backpressure kicks in."""
        return self._max_buffer_size


# ----------------------------------------------------------------------
# Module helpers
# ----------------------------------------------------------------------


def _require_thread_id(config: RunnableConfig) -> str:
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if thread_id is None:
        thread_id = (config or {}).get("thread_id")
    if thread_id is None:
        raise ValueError("config must contain a thread_id")
    return str(thread_id)


def _require_checkpoint_id(checkpoint: Checkpoint) -> str:
    checkpoint_id = checkpoint.get("id")
    if not checkpoint_id:
        raise ValueError("checkpoint must contain an id")
    return str(checkpoint_id)


def _as_uuid(value: Any, field: str) -> uuid.UUID:
    """Coerce a LangGraph id to the ``UUID`` type used by ``agent_checkpoints``."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(
            f"{field} must be a UUID (agent_checkpoints.thread_id/checkpoint_id "
            f"are UUID columns), got {value!r}"
        ) from exc


def _as_optional_uuid(value: Any, field: str) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return _as_uuid(value, field)


def _parse_timestamp(value: Any) -> datetime:
    """Parse a LangGraph ISO-8601 ``ts`` into a timezone-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            # fromisoformat parses a trailing "Z" natively on Python 3.11+.
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(UTC)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _before_timestamp(before: RunnableConfig | None) -> datetime | None:
    """Extract the ``created_at`` cut-off from a ``before`` config, if present."""
    if not before:
        return None
    configurable = before.get("configurable", {}) if isinstance(before, dict) else {}
    checkpoint_id = configurable.get("checkpoint_id")
    if not checkpoint_id:
        return None
    # ``ts`` is only recoverable from the stored row, so the caller falls back to
    # an unbounded scan when only an id is supplied.
    return _parse_timestamp(configurable.get("ts"))


def _dump_state(serde: SerializerProtocol, checkpoint: Checkpoint) -> str:
    """Serialize a checkpoint into a JSONB-safe ``{"type", "data"}`` envelope.

    ``serde.dumps_typed`` returns ``(type, bytes)``; ``state`` is a JSONB column,
    so the payload is base64-encoded. Round-tripped by :func:`_load_state`.
    """
    type_tag, payload = serde.dumps_typed(checkpoint)
    return json.dumps({"type": type_tag, "data": base64.b64encode(payload).decode("ascii")})


def _as_dict(value: Any) -> dict[str, Any]:
    """Decode a JSONB column into a dict.

    asyncpg returns ``jsonb``/``json`` as ``str`` unless a codec is installed on
    the pool, and that pool is owned by the application and shared with the rest
    of the app. Decoding here keeps this checkpointer working either way instead
    of mutating global pool state.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray, str)):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            logger.warning("checkpoint metadata is not valid JSON, ignoring: %r", value)
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _load_state(serde: SerializerProtocol, state: Any) -> Checkpoint:
    """Inverse of :func:`_dump_state`."""
    if isinstance(state, (bytes, bytearray)):
        state = json.loads(state.decode("utf-8"))
    elif isinstance(state, str):
        state = json.loads(state)
    return serde.loads_typed((state["type"], base64.b64decode(state["data"])))


def _flush_args(serde: SerializerProtocol, pending: _PendingCheckpoint) -> tuple[Any, ...]:
    """Build the six ``$1..$6`` arguments for one ``agent_checkpoints`` row."""
    return (
        pending.thread_id,
        pending.checkpoint_id,
        pending.parent_id,
        _dump_state(serde, pending.checkpoint),
        json.dumps(pending.metadata, default=str, ensure_ascii=False),
        pending.created_at,
    )


def _load_checkpoint(serde: SerializerProtocol, row: Any) -> Checkpoint:
    return _load_state(serde, row["state"])


def _row_to_tuple(serde: SerializerProtocol, row: Any, thread_id: str) -> CheckpointTuple:
    metadata = _as_dict(row["metadata"])
    parent_id = row["parent_id"]
    return CheckpointTuple(
        config={
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": str(row["checkpoint_id"]),
            }
        },
        checkpoint=_load_checkpoint(serde, row),
        metadata=metadata,
        parent_config=(
            {"configurable": {"thread_id": thread_id, "checkpoint_id": str(parent_id)}}
            if parent_id
            else None
        ),
        pending_writes=None,
    )


def _matches_filter(metadata: CheckpointMetadata | dict | None, filter: dict[str, Any]) -> bool:
    """Check metadata against LangGraph's simple ``key == value`` filter semantics."""
    if not filter:
        return True
    metadata = metadata or {}
    for key, expected in filter.items():
        if key not in metadata:
            return False
        if isinstance(expected, (list, tuple, set)):
            if metadata[key] not in expected:
                return False
        elif metadata[key] != expected:
            return False
    return True
