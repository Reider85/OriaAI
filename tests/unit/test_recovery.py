"""Unit tests for the B-5 recovery protocol (``RedisPostgresCheckpointer.recover``).

The two layers are replaced with in-memory fakes so each recovery branch —
Redis newer, PG newer, conflict, Redis down, timeout, corrupted state — can be
driven deterministically. Docker-backed crash scenarios live in
``tests/integration/test_recovery_integration.py``.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from llm_client.orchestration.checkpointers.composite import (
    RedisPostgresCheckpointer,
    _compare_timestamps,
    _is_valid_checkpoint,
)
from llm_client.orchestration.checkpointers.metrics import NullCheckpointMetrics
from llm_client.orchestration.checkpointers.postgres_checkpointer import PostgresCheckpointer
from llm_client.orchestration.checkpointers.redis_checkpointer import RedisCheckpointer

# ── Test doubles ─────────────────────────────────────────────────────────────


class FakeTuple:
    """Stand-in for ``CheckpointTuple`` (attribute access, as LangGraph uses)."""

    def __init__(self, config: dict, checkpoint: dict, metadata: dict) -> None:
        self.config = config
        self.checkpoint = checkpoint
        self.metadata = metadata
        self.parent_config = None
        self.pending_writes = None


class FakeLayer:
    """In-memory checkpointer layer exposing only what ``recover()`` calls."""

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        corrupt: bool = False,
        corrupt_on_read_only: bool = False,
    ) -> None:
        self.name = name
        self.available = available
        self.corrupt = corrupt
        # Corrupts only what comes back out of a read, leaving stored values
        # intact — models a row that was damaged in the store, not one that was
        # never written correctly.
        self.corrupt_on_read_only = corrupt_on_read_only
        # Once a replay lands, stop serving reads — models the durable copy
        # becoming unreadable between the write and the validation read-back.
        self.drop_after_replay = False
        # thread_id -> FakeTuple (latest only; recovery never needs history)
        self.threads: dict[str, FakeTuple] = {}
        self.replayed: list[tuple[str, str]] = []

    def _maybe_corrupt(self, found: FakeTuple) -> FakeTuple:
        if self.corrupt or self.corrupt_on_read_only:
            # Shape-check failure: a checkpoint that lost its id.
            return FakeTuple(found.config, {"ts": found.checkpoint.get("ts")}, found.metadata)
        return found

    async def aget_tuple(self, config: dict) -> FakeTuple | None:
        if not self.available:
            raise ConnectionError(f"{self.name} unavailable")
        found = self.threads.get(config["configurable"]["thread_id"])
        return self._maybe_corrupt(found) if found is not None else None

    async def aget(self, config: dict) -> dict | None:
        if not self.available or self.drop_after_replay:
            return None
        found = self.threads.get(config["configurable"]["thread_id"])
        if found is None:
            return None
        return self._maybe_corrupt(found).checkpoint

    async def aput(self, config: dict, checkpoint: dict, metadata: dict) -> dict:
        if not self.available:
            raise ConnectionError(f"{self.name} unavailable")
        thread_id = config["configurable"]["thread_id"]
        self.threads[thread_id] = FakeTuple(config, checkpoint, metadata)
        return config

    async def list_active_thread_ids(self, within_seconds: int = 86400) -> list[str]:
        if not self.available:
            raise ConnectionError(f"{self.name} unavailable")
        return sorted(self.threads)

    async def list_all_thread_ids(self) -> list[str]:
        if not self.available:
            raise ConnectionError(f"{self.name} unavailable")
        return sorted(self.threads)

    async def replay_checkpoint(
        self, thread_id: str, checkpoint: dict, metadata: dict | None = None
    ) -> None:
        if not self.available:
            raise ConnectionError(f"{self.name} unavailable")
        self.replayed.append((thread_id, checkpoint["id"]))
        await self.aput(
            {"configurable": {"thread_id": thread_id}},
            checkpoint,
            metadata or {},
        )


def make_checkpoint(offset_seconds: float = 0.0) -> dict:
    """A minimal but valid LangGraph-shaped checkpoint.

    ``id`` is a bare UUID because ``agent_checkpoints.checkpoint_id`` is a UUID
    column — the layer-level tests below exercise the real saver, which rejects
    anything else.
    """
    ts = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return {
        "id": str(uuid.uuid4()),
        "ts": ts.isoformat(),
        "channel_values": {},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": [],
    }


def build(redis: FakeLayer, pg: FakeLayer, **kwargs: Any) -> RedisPostgresCheckpointer:
    return RedisPostgresCheckpointer(
        redis_checkpointer=redis,
        postgres_checkpointer=pg,
        metrics=NullCheckpointMetrics(),
        **kwargs,
    )


def seed(layer: FakeLayer, thread_id: str, checkpoint: dict, metadata: dict | None = None):
    layer.threads[thread_id] = FakeTuple(
        {"configurable": {"thread_id": thread_id}}, checkpoint, metadata or {"source": layer.name}
    )


# ── Timestamp ordering ───────────────────────────────────────────────────────


class TestCompareTimestamps:
    def test_redis_newer_returns_positive(self):
        assert _compare_timestamps(make_checkpoint(10), make_checkpoint(0)) == 1

    def test_pg_newer_returns_negative(self):
        assert _compare_timestamps(make_checkpoint(0), make_checkpoint(10)) == -1

    def test_equal_timestamps_return_zero(self):
        frozen = datetime(2026, 9, 27, 12, 0, tzinfo=UTC).isoformat()
        a = {**make_checkpoint(), "ts": frozen}
        b = {**make_checkpoint(), "ts": frozen}
        assert _compare_timestamps(a, b) == 0

    def test_microsecond_skew_is_treated_as_equal(self):
        # Two writes of the same transition can differ by a few microseconds
        # depending on which layer serialised first; that is not a real conflict.
        base = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
        a = {**make_checkpoint(), "ts": base.isoformat()}
        b = {**make_checkpoint(), "ts": (base + timedelta(microseconds=400)).isoformat()}
        assert _compare_timestamps(a, b) == 0

    def test_unparseable_timestamp_falls_back_to_conflict_path(self):
        # Unorderable state must not be treated as "Redis wins" — it routes to
        # the PG-wins conflict branch instead.
        broken = {**make_checkpoint(), "ts": "not-a-timestamp"}
        assert _compare_timestamps(broken, make_checkpoint(0)) == 0

    def test_missing_timestamp_is_not_ordered(self):
        undated = {k: v for k, v in make_checkpoint().items() if k != "ts"}
        assert _compare_timestamps(undated, make_checkpoint(0)) == 0

    def test_naive_timestamp_is_treated_as_utc(self):
        # Deliberately naive: LangGraph should never emit one, but a
        # misconfigured writer must not make the state unrecoverable.
        base = datetime(2026, 9, 27, 12, 0)  # noqa: DTZ001
        naive = {**make_checkpoint(), "ts": base.isoformat()}
        aware = {**make_checkpoint(), "ts": base.replace(tzinfo=UTC).isoformat()}
        assert _compare_timestamps(naive, aware) == 0


class TestIsValidCheckpoint:
    def test_accepts_well_formed_checkpoint(self):
        assert _is_valid_checkpoint(make_checkpoint()) is True

    def test_rejects_missing_id(self):
        cp = make_checkpoint()
        del cp["id"]
        assert _is_valid_checkpoint(cp) is False

    def test_rejects_wrong_channel_values_type(self):
        cp = make_checkpoint()
        cp["channel_values"] = "not-a-mapping"
        assert _is_valid_checkpoint(cp) is False

    def test_rejects_non_dict(self):
        assert _is_valid_checkpoint("corrupted") is False


# ── Recovery: per-thread reconciliation ──────────────────────────────────────


class TestRecoverPerThread:
    async def test_redis_newer_is_replayed_into_postgres(self):
        """Scenario 1 (planned restart): Redis holds writes PG has not flushed yet."""
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))
        seed(redis, thread_id, make_checkpoint(5))

        stats = await build(redis, pg).recover()

        assert stats["redis_delta_replayed"] == 1
        assert stats["pg_checkpoints_recovered"] == 0
        assert pg.threads[thread_id].checkpoint["ts"] == redis.threads[thread_id].checkpoint["ts"]
        assert pg.replayed == [(thread_id, redis.threads[thread_id].checkpoint["id"])]

    async def test_pg_newer_keeps_snapshot_and_ignores_stale_redis(self):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        pg_cp = make_checkpoint(30)
        seed(pg, thread_id, pg_cp)
        seed(redis, thread_id, make_checkpoint(0))

        stats = await build(redis, pg).recover()

        assert stats["pg_checkpoints_recovered"] == 1
        assert stats["redis_delta_replayed"] == 0
        # Redis is not rewritten: it expires naturally and stays a read cache.
        assert pg.replayed == []
        assert pg.threads[thread_id].checkpoint["id"] == pg_cp["id"]

    async def test_thread_unknown_to_postgres_is_replayed_in_full(self):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(redis, thread_id, make_checkpoint(1))

        stats = await build(redis, pg).recover()

        assert stats["redis_delta_replayed"] == 1
        assert thread_id in pg.threads

    async def test_identical_state_in_both_layers_is_a_no_op(self):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        frozen = make_checkpoint(0)
        seed(pg, thread_id, frozen)
        seed(redis, thread_id, dict(frozen))

        stats = await build(redis, pg).recover()

        assert stats["pg_checkpoints_recovered"] == 1
        assert stats["conflicts_resolved"] == 0
        assert pg.replayed == []

    async def test_equal_timestamp_different_content_resolves_to_pg(self):
        """The rare conflict: same instant, divergent content. PG wins."""
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        base = datetime(2026, 9, 27, 12, 0, tzinfo=UTC).isoformat()
        pg_cp = {**make_checkpoint(), "ts": base}
        redis_cp = {**make_checkpoint(), "ts": base, "channel_values": {"messages": ["other"]}}
        seed(pg, thread_id, pg_cp)
        seed(redis, thread_id, redis_cp)

        stats = await build(redis, pg).recover()

        assert stats["conflicts_resolved"] == 1
        # The Redis copy is overwritten from the durable layer.
        assert redis.threads[thread_id].checkpoint["id"] == pg_cp["id"]
        # And the durable state is untouched.
        assert pg.threads[thread_id].checkpoint["id"] == pg_cp["id"]

    async def test_multiple_threads_are_all_recovered(self):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        threads = [str(uuid.uuid4()) for _ in range(5)]
        for i, thread_id in enumerate(threads):
            seed(pg, thread_id, make_checkpoint(0))
            if i % 2 == 0:
                seed(redis, thread_id, make_checkpoint(10))
            else:
                seed(redis, thread_id, make_checkpoint(-10))

        stats = await build(redis, pg).recover()

        assert stats["redis_delta_replayed"] == 3
        assert stats["pg_checkpoints_recovered"] == 2
        assert stats["threads_skipped"] == 0


# ── Recovery: degraded layers (B-5 scenarios 2 and 3) ───────────────────────


class TestRecoverDegradedLayers:
    async def test_redis_down_falls_back_to_postgres_only(self):
        """Scenario 2 (Redis crash): no delta available, snapshot still serves."""
        redis, pg = FakeLayer("redis", available=False), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))

        stats = await build(redis, pg).recover()

        assert stats["redis_delta_replayed"] == 0
        assert stats["pg_checkpoints_recovered"] == 1
        assert stats["threads_skipped"] == 0

    async def test_redis_down_still_recovers_threads_known_to_postgres(self):
        """Redis being unreachable must not drop durable threads from the pass."""
        redis, pg = FakeLayer("redis", available=False), FakeLayer("pg")
        threads = [str(uuid.uuid4()) for _ in range(3)]
        for thread_id in threads:
            seed(pg, thread_id, make_checkpoint(0))

        stats = await build(redis, pg).recover()

        assert stats["pg_checkpoints_recovered"] == 3

    async def test_postgres_down_still_recovers_from_redis(self):
        """Scenario 3 (PG crash): Redis is the only layer holding recent writes."""
        redis, pg = FakeLayer("redis"), FakeLayer("pg", available=False)
        thread_id = str(uuid.uuid4())
        seed(redis, thread_id, make_checkpoint(0))

        stats = await build(redis, pg).recover()

        # Redis threads are still examined, but the replay cannot land, so the
        # thread is reported as unreconciled rather than falsely "replayed".
        assert stats["redis_delta_replayed"] == 0
        assert stats["pg_checkpoints_recovered"] == 0
        assert stats["threads_skipped"] == 1

    async def test_both_layers_down_yields_zeroed_stats(self):
        """Scenario 4 (simultaneous failure): reported, not raised."""
        redis = FakeLayer("redis", available=False)
        pg = FakeLayer("pg", available=False)

        stats = await build(redis, pg).recover()

        assert stats == {
            "pg_checkpoints_recovered": 0,
            "redis_delta_replayed": 0,
            "conflicts_resolved": 0,
            "corrupted_states": 0,
            "threads_skipped": 0,
        }

    async def test_expired_redis_key_recovers_from_postgres(self):
        """TTL expiry: the checkpoint is gone from Redis, PG still has it."""
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))
        # Nothing seeded in Redis — as if the key aged out.

        stats = await build(redis, pg).recover()

        assert stats["pg_checkpoints_recovered"] == 1
        assert pg.replayed == []


# ── Recovery: timeout and validation ─────────────────────────────────────────


class TestRecoverTimeout:
    async def test_timeout_stops_the_pass_and_reports_remainder(self, monkeypatch):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        for _ in range(10):
            thread_id = str(uuid.uuid4())
            seed(pg, thread_id, make_checkpoint(0))

        # Force the deadline into the past after the first thread is handled by
        # advancing the clock past zero on the second call.
        ticks = iter([0.0, 0.0, 0.0, 100.0, 100.0, 100.0])
        monkeypatch.setattr(
            "llm_client.orchestration.checkpointers.composite.time.perf_counter",
            lambda: next(ticks, 100.0),
        )

        stats = await build(redis, pg).recover(timeout_seconds=30.0)

        assert stats["threads_skipped"] > 0
        assert stats["pg_checkpoints_recovered"] + stats["threads_skipped"] <= 10

    async def test_zero_timeout_skips_everything_without_raising(self):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))

        stats = await build(redis, pg).recover(timeout_seconds=0.0)

        assert stats["threads_skipped"] == 1
        assert stats["pg_checkpoints_recovered"] == 0

    async def test_partial_recovery_still_returns_useful_stats(self):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        for i in range(4):
            thread_id = str(uuid.uuid4())
            seed(pg, thread_id, make_checkpoint(i))
            seed(redis, thread_id, make_checkpoint(i + 10))

        stats = await build(redis, pg).recover(timeout_seconds=5.0)

        assert stats["redis_delta_replayed"] == 4
        assert stats["threads_skipped"] == 0


class TestRecoverValidation:
    async def test_corrupt_source_checkpoint_is_not_replayed(self):
        """A checkpoint that fails the shape check is never promoted to durable."""
        redis = FakeLayer("redis", corrupt=True)
        pg = FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(redis, thread_id, make_checkpoint(5))
        pg_before = make_checkpoint(0)
        seed(pg, thread_id, pg_before)

        stats = await build(redis, pg).recover()

        assert stats["corrupted_states"] == 1
        assert stats["redis_delta_replayed"] == 0
        # The good snapshot survives — a bad delta must not overwrite it.
        assert pg.threads[thread_id].checkpoint["id"] == pg_before["id"]

    async def test_corrupt_checkpoint_for_unknown_thread_is_flagged(self):
        redis = FakeLayer("redis", corrupt=True)
        pg = FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(redis, thread_id, make_checkpoint(5))

        stats = await build(redis, pg).recover()

        assert stats["corrupted_states"] == 1
        assert thread_id not in pg.threads

    async def test_readback_corruption_after_replay_is_flagged(self):
        """A state that is unreadable once recovery wrote it is flagged, not trusted."""
        redis = FakeLayer("redis")
        pg = FakeLayer("pg", corrupt_on_read_only=True)
        thread_id = str(uuid.uuid4())
        seed(redis, thread_id, make_checkpoint(5))

        # After the replay lands both layers go dark, so the read-back that a
        # resumed run would perform has nothing usable to return.
        redis.drop_after_replay = True
        pg.drop_after_replay = True

        stats = await build(redis, pg).recover()

        assert stats["redis_delta_replayed"] == 1
        assert stats["corrupted_states"] == 1

    async def test_healthy_redis_masks_a_damaged_durable_copy(self):
        """The hot layer still serves the graph, so PG damage is not fatal."""
        redis = FakeLayer("redis")
        pg = FakeLayer("pg", corrupt_on_read_only=True)
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))
        seed(redis, thread_id, make_checkpoint(5))

        stats = await build(redis, pg).recover()

        assert stats["redis_delta_replayed"] == 1
        assert stats["corrupted_states"] == 0

    async def test_healthy_replay_does_not_flag_corruption(self):
        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))
        seed(redis, thread_id, make_checkpoint(5))

        stats = await build(redis, pg).recover()

        assert stats["corrupted_states"] == 0

    async def test_needs_human_review_event_is_emitted(self):
        events: list[dict] = []

        class Recorder:
            async def write(self, event: dict) -> None:
                events.append(event)

        redis = FakeLayer("redis", corrupt=True)
        pg = FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(redis, thread_id, make_checkpoint(5))

        await build(redis, pg, operational_writer=Recorder()).recover()
        await asyncio.sleep(0)

        flagged = [e for e in events if e["event"] == "checkpoint_recovery_needs_human_review"]
        assert len(flagged) == 1
        assert flagged[0]["thread_id"] == thread_id
        assert flagged[0]["reason"] == "corrupted_source_checkpoint"


# ── Recovery: operational logging ────────────────────────────────────────────


class TestRecoverOperationalEvents:
    async def test_recovery_emits_per_thread_and_summary_events(self):
        events: list[dict] = []

        class Recorder:
            async def write(self, event: dict) -> None:
                events.append(event)

        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))
        seed(redis, thread_id, make_checkpoint(5))

        await build(redis, pg, operational_writer=Recorder()).recover()
        await asyncio.sleep(0)  # let create_task'd events land

        kinds = [e["event"] for e in events]
        assert "checkpoint_recovery" in kinds
        recovery_event = next(e for e in events if e["event"] == "checkpoint_recovery")
        assert recovery_event["thread_id"] == thread_id
        assert recovery_event["delta_replayed"] is True

    async def test_conflict_emits_winner_and_reason(self):
        events: list[dict] = []

        class Recorder:
            async def write(self, event: dict) -> None:
                events.append(event)

        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        base = datetime(2026, 9, 27, 12, 0, tzinfo=UTC).isoformat()
        seed(pg, thread_id, {**make_checkpoint(), "ts": base})
        seed(redis, thread_id, {**make_checkpoint(), "ts": base, "channel_values": {"messages": ["other"]}})

        await build(redis, pg, operational_writer=Recorder()).recover()
        await asyncio.sleep(0)

        conflict = next(e for e in events if e["event"] == "checkpoint_conflict")
        assert conflict["winner"] == "pg"
        assert conflict["reason"] == "content_diff"
        assert conflict["thread_id"] == thread_id

    async def test_broken_operational_writer_does_not_break_recovery(self):
        class BrokenWriter:
            async def write(self, event: dict) -> None:
                raise RuntimeError("sink down")

        redis, pg = FakeLayer("redis"), FakeLayer("pg")
        thread_id = str(uuid.uuid4())
        seed(pg, thread_id, make_checkpoint(0))
        seed(redis, thread_id, make_checkpoint(5))

        stats = await build(redis, pg, operational_writer=BrokenWriter()).recover()

        assert stats["redis_delta_replayed"] == 1


# ── Layer-level helpers added for B-5 ────────────────────────────────────────


class TestListActiveThreadIds:
    """``PostgresCheckpointer.list_active_thread_ids`` seeds the recovery pass."""

    @staticmethod
    def _saver(rows):
        saver = PostgresCheckpointer.__new__(PostgresCheckpointer)
        recorded: dict[str, Any] = {}

        async def fetch(sql, *args):
            recorded["sql"] = sql
            recorded["args"] = args
            return rows

        saver._pg_pool = SimpleNamespace(fetch=fetch)
        return saver, recorded

    async def test_returns_thread_ids_as_strings(self):
        tid = uuid.uuid4()
        saver, _ = self._saver([{"thread_id": tid}])

        assert await saver.list_active_thread_ids() == [str(tid)]

    async def test_passes_the_window_as_a_bound_parameter(self):
        """The window is multiplied into an interval, never interpolated as text."""
        saver, recorded = self._saver([])

        await saver.list_active_thread_ids(within_seconds=3600)

        sql, args = recorded["sql"], recorded["args"]
        assert "INTERVAL" in sql
        assert "$1" in sql
        assert args == (3600,)
        # No caller-supplied value may reach the statement text.
        assert "3600" not in sql

    async def test_defaults_to_the_redis_ttl_window(self):
        saver, recorded = self._saver([])

        await saver.list_active_thread_ids()

        assert recorded["args"] == (86400,)

    async def test_rejects_a_negative_window(self):
        saver, _ = self._saver([])

        with pytest.raises(ValueError):
            await saver.list_active_thread_ids(within_seconds=-1)

    async def test_empty_result_is_an_empty_list(self):
        saver, _ = self._saver([])

        assert await saver.list_active_thread_ids() == []


class TestListAllThreadIds:
    """``RedisCheckpointer.list_all_thread_ids`` finds threads PG has not seen."""

    @staticmethod
    def _saver(pages):
        """*pages* maps an incoming cursor to the ``(next_cursor, keys)`` pair SCAN returns."""
        saver = RedisCheckpointer.__new__(RedisCheckpointer)
        seen_cursors: list[int] = []

        async def scan(cursor=0, match=None, count=None):
            seen_cursors.append(cursor)
            return pages[cursor]

        saver._redis_client = SimpleNamespace(scan=scan)
        return saver, seen_cursors

    async def test_extracts_thread_from_the_latest_index_key(self):
        tid = str(uuid.uuid4())
        saver, _ = self._saver({0: (0, [f"checkpoint:{tid}:latest".encode()])})

        assert await saver.list_all_thread_ids() == [tid]

    async def test_ignores_per_checkpoint_keys(self):
        tid = str(uuid.uuid4())
        saver, _ = self._saver(
            {0: (0, [f"checkpoint:{tid}:cp-1".encode(), f"checkpoint:{tid}:cp-2".encode()])}
        )

        assert await saver.list_all_thread_ids() == []

    async def test_follows_the_scan_cursor_to_completion(self):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        saver, cursors = self._saver(
            {
                0: (7, [f"checkpoint:{a}:latest".encode()]),
                7: (0, [f"checkpoint:{b}:latest".encode()]),
            }
        )

        found = await saver.list_all_thread_ids()

        assert set(found) == {a, b}
        # A single pass would have missed the second page.
        assert cursors == [0, 7]

    async def test_deduplicates_repeated_keys(self):
        tid = str(uuid.uuid4())
        key = f"checkpoint:{tid}:latest".encode()
        saver, _ = self._saver({0: (0, [key, key])})

        assert await saver.list_all_thread_ids() == [tid]

    async def test_handles_str_keys_from_a_decode_responses_client(self):
        tid = str(uuid.uuid4())
        saver, _ = self._saver({0: (0, [f"checkpoint:{tid}:latest"])})

        assert await saver.list_all_thread_ids() == [tid]

    async def test_ignores_malformed_keys(self):
        saver, _ = self._saver({0: (0, [b"checkpoint::latest", b"noise", b"a:b:c:d:latest"])})

        assert await saver.list_all_thread_ids() == []

    async def test_empty_keyspace_yields_nothing(self):
        saver, _ = self._saver({0: (0, [])})

        assert await saver.list_all_thread_ids() == []


class TestReplayCheckpoint:
    """``PostgresCheckpointer.replay_checkpoint`` buffers a recovered delta."""

    @staticmethod
    def _saver():
        saver = PostgresCheckpointer.__new__(PostgresCheckpointer)
        saver._buffer = {}
        saver._writes_buffer = {}
        saver._panic_mode = False
        saver._max_buffer_size = 100
        saver._metrics = None
        saver.flush_batch_size = 1000
        saver._buffer_not_full = asyncio.Condition()
        return saver

    async def test_buffers_the_checkpoint_without_touching_postgres(self):
        saver = self._saver()
        cp = make_checkpoint()

        await saver.replay_checkpoint(str(uuid.uuid4()), cp, {"step": 1})

        assert len(saver._buffer) == 1
        assert next(iter(saver._buffer.values())).checkpoint["id"] == cp["id"]

    async def test_defaults_metadata_to_an_empty_mapping(self):
        saver = self._saver()

        await saver.replay_checkpoint(str(uuid.uuid4()), make_checkpoint())

        assert next(iter(saver._buffer.values())).metadata == {}

    async def test_replayed_checkpoint_is_readable_from_the_buffer(self):
        saver = self._saver()
        thread_id = str(uuid.uuid4())
        cp = make_checkpoint()

        await saver.replay_checkpoint(thread_id, cp, {"step": 1})
        read_back = await saver.aget({"configurable": {"thread_id": thread_id}})

        assert read_back["id"] == cp["id"]
