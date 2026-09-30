"""B-6/E-2: checkpoint recovery integration tests (4 scenarios).

Integration tests for the B-5 recovery protocol against real Redis + PostgreSQL.
Covers the four restart/failure scenarios (planned restart, Redis crash, PG
crash, simultaneous crash). Every test skips when the backing services are not
reachable, so the suite stays green on a laptop with nothing but docker-compose
down.

Scenarios are reproduced by killing the Docker containers (SIGKILL) and
restarting, which simulates process failure. Real process restart is simulated
by creating a new RedisPostgresCheckpointer instance. Each run emits a
structured JSON report to ``reports/recovery_<scenario>_<date>.json`` for the
E-2 nightly CI trend tracking.

Uses subprocess.run for docker commands (per B-6/E-2 guidance). Container names
are resolved dynamically so the suite works both locally (docker-compose
``llm-redis``/``llm-postgres``) and on GitHub Actions per-job service
containers (generated names).
"""

import asyncio
import json
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import pytest
import redis.asyncio as aioredis

from llm_client.config import Settings
from llm_client.orchestration.checkpointers.composite import RedisPostgresCheckpointer
from llm_client.orchestration.checkpointers.factory import build_checkpointer

pytestmark = [pytest.mark.staging_load]

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"

REDIS_URL = os.getenv("REDIS_CHECKPOINT_URL", "redis://127.0.0.1:6379/1")
PG_DSN_ASYNC = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5434/llm_client"
)
PG_DSN = PG_DSN_ASYNC.replace("postgresql+asyncpg://", "postgresql://").split("?")[0]

# logical names -> (well-known docker-compose name, image fragment, container port)
_CONTAINER_HINTS = {
    "redis": ("llm-redis", "redis:", "6379"),
    "postgres": ("llm-postgres", "postgres:", "5432"),
}

AGENT_CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    thread_id UUID NOT NULL,
    checkpoint_id UUID NOT NULL,
    parent_id UUID,
    state JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP(timezone=True) NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_id)
);
"""


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_checkpoint(offset_seconds: float = 0.0) -> dict:
    """A valid LangGraph-shaped checkpoint with a distinct, ordered timestamp."""
    ts = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC) + timedelta(seconds=offset_seconds)
    return {
        "id": str(uuid.uuid4()),
        "ts": ts.isoformat(),
        "channel_values": {"messages": ["hello"]},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": [],
    }


def config_for(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def _services_ready() -> bool:
    """Check if Redis and PostgreSQL are available."""
    redis_ok = False
    pg_ok = False
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
        await redis_client.ping()
        await redis_client.aclose()
        redis_ok = True
    except Exception:  # noqa: BLE001 - any driver error means "not reachable"
        redis_ok = False

    try:
        conn = await asyncpg.connect(PG_DSN)
        await conn.close()
        pg_ok = True
    except Exception:  # noqa: BLE001 - any driver error means "not reachable"
        pg_ok = False

    return redis_ok and pg_ok


async def _flush_redis_checkpoint_db() -> None:
    """Drop whatever the restarted Redis replays so the crash scenario is exact.

    A Redis crash in B-5 means the hot layer lost its in-memory state and the
    PostgreSQL snapshot alone must carry recovery. Local docker-compose runs
    Redis with AOF (Block A-1), which can replay *part* of the checkpoint set
    and turn the ``aget`` read-path into a stale-first read. Flushing DB 1 after
    the restart makes the test deterministic and mirrors the CI service
    container (no persistence): Redis comes back empty, PG is the source.
    """
    client = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.flushdb()
    finally:
        await client.aclose()


def _resolve_container(logical_name: str) -> str:
    """Find the actual Docker container name for a service.

    docker-compose names containers ``llm-redis`` / ``llm-postgres`` locally;
    GitHub Actions runs each job's service containers under generated names, so
    we fall back to matching by image fragment or exposed port.
    """
    well_known, image_fragment, port = _CONTAINER_HINTS[logical_name]
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        pytest.fail(f"docker ps failed while resolving {logical_name}: {exc}")

    rows = [line.split("\t", maxsplit=2) for line in out.strip().splitlines() if line.strip()]
    for name, _, _ in rows:
        if name == well_known:
            return name
    for name, image, ports in rows:
        if image_fragment in image or f"->{port}/tcp" in ports:
            return name
    pytest.fail(
        f"Could not locate the {logical_name} container "
        f"(looked for name {well_known}, image {image_fragment}, port {port})"
    )


def _kill_container(logical_name: str) -> None:
    """Kill a Docker container with SIGKILL."""
    container = _resolve_container(logical_name)
    try:
        subprocess.run(
            ["docker", "kill", container],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"Failed to kill {container}: {exc}")


def _restart_container(logical_name: str) -> None:
    """Restart a Docker container."""
    container = _resolve_container(logical_name)
    try:
        subprocess.run(
            ["docker", "restart", container],
            check=True,
            capture_output=True,
            timeout=30,
        )
        # Wait for health check
        time.sleep(5)
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"Failed to restart {container}: {exc}")


def _build_checkpointer() -> RedisPostgresCheckpointer:
    """Build a fresh RedisPostgresCheckpointer (simulates process restart)."""
    settings = Settings()
    settings.checkpoint_backend = os.getenv("CHECKPOINT_BACKEND", "redis_postgres")
    settings.redis_checkpoint_url = REDIS_URL
    settings.database_url = PG_DSN_ASYNC
    settings.redis_checkpoint_ttl_seconds = 86400
    settings.checkpoint_flush_interval_seconds = 5
    settings.checkpoint_flush_batch_size = 50

    bundle = build_checkpointer(settings)
    if not bundle.checkpointer or not isinstance(bundle.checkpointer, RedisPostgresCheckpointer):
        pytest.fail("Could not build RedisPostgresCheckpointer")

    return bundle.checkpointer


async def _write_checkpoints(
    checkpointer: RedisPostgresCheckpointer, thread_id: str, count: int = 10
):
    """Write N checkpoints for a thread, flushing PG after each write.

    The explicit flush mirrors a live background flusher (B-4) and makes the
    crash-scenario verification deterministic regardless of AOF fsync timing,
    so a Redis SIGKILL never silently wipes the whole expectation set.
    """
    checkpoints = []
    for i in range(count):
        checkpoint = make_checkpoint(i * 0.1)  # 0.1s apart
        config = config_for(thread_id)
        await checkpointer.aput(config, checkpoint, {"node": f"node_{i}"})
        await checkpointer._postgres._flush()
        checkpoints.append(checkpoint)
    return checkpoints


async def _verify_recovery(
    checkpointer: RedisPostgresCheckpointer, thread_id: str, original_checkpoints: list
) -> dict:
    """Verify that recovery restored all checkpoints; return the newest one."""
    config = config_for(thread_id)

    # Get the latest checkpoint
    recovered = await checkpointer.aget(config)
    assert recovered is not None, "Recovery failed: no checkpoint found"

    # Verify the checkpoint matches the last one we wrote
    original_last = original_checkpoints[-1]
    assert recovered["id"] == original_last["id"], "Recovery: wrong checkpoint ID"
    assert recovered["channel_values"] == original_last["channel_values"], "Recovery: wrong state"

    # Verify we can list all checkpoints
    all_checkpoints = list(checkpointer.alist(config, limit=100))
    assert len(all_checkpoints) >= len(original_checkpoints), "Recovery: missing checkpoints"

    return recovered


def _write_json_report(report: dict) -> None:
    """Persist a structured JSON report for the scenario run (E-2 reporting)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    target = REPORTS_DIR / f"recovery_{report['scenario']}_{date}.json"
    with target.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)


def _data_loss_seconds(original_checkpoints: list, recovered: dict | None) -> float:
    """Estimate the recovery data-loss window (latest expected vs recovered ts)."""
    expected_ts = datetime.fromisoformat(original_checkpoints[-1]["ts"])
    if not isinstance(recovered, dict) or "ts" not in recovered:
        return 0.0
    recovered_ts = datetime.fromisoformat(recovered["ts"])
    return round(max(0.0, (expected_ts - recovered_ts).total_seconds()), 3)


async def _run_scenario(
    *,
    scenario: str,
    kill_redis: bool,
    kill_pg: bool,
    threads: int = 1,
    samples: int = 10,
    reset_redis_after_restart: bool = False,
) -> dict:
    """Execute one B-5 recovery scenario end-to-end and return its JSON report.

    Report is written to ``reports/recovery_<scenario>_<date>.json`` before the
    test returns or raises, so a failed run still records a FAIL report for the
    nightly trend. The original exception (if any) is re-raised so the pytest
    failure stays visible.

    ``reset_redis_after_restart`` is True for the scenarios where Redis crashed:
    the hot layer is treated as having lost its state (B-5's accepted-loss
    model), so the restarted Redis DB is flushed before recovery runs and the
    PostgreSQL snapshot alone must carry the pass.
    """
    report: dict = {
        "scenario": scenario,
        "timestamp": datetime.now(UTC).isoformat(),
        "threads": threads,
        "samples_per_thread": samples,
        "passed": True,
    }
    thread_ids = [f"b6-recovery-{scenario}-{uuid.uuid4().hex[:8]}" for _ in range(threads)]
    checkpointer = _build_checkpointer()
    try:
        original = {}
        for thread_id in thread_ids:
            original[thread_id] = await _write_checkpoints(checkpointer, thread_id, samples)

        if kill_redis:
            _kill_container("redis")
        if kill_pg:
            _kill_container("postgres")
        await asyncio.sleep(1)
        if kill_redis:
            _restart_container("redis")
        if kill_pg:
            _restart_container("postgres")
        if reset_redis_after_restart:
            await _flush_redis_checkpoint_db()

        fresh = _build_checkpointer()
        started = time.perf_counter()
        stats = await fresh.recover(timeout_seconds=30.0)
        report["elapsed_s"] = round(time.perf_counter() - started, 3)
        report["recovery_time_s"] = report["elapsed_s"]
        for key in (
            "pg_checkpoints_recovered",
            "redis_delta_replayed",
            "conflicts_resolved",
            "corrupted_states",
            "threads_skipped",
        ):
            report[key] = stats.get(key, 0)

        for thread_id in thread_ids:
            recovered = await _verify_recovery(fresh, thread_id, original[thread_id])
            report["data_loss_s"] = _data_loss_seconds(original[thread_id], recovered)
    except Exception as exc:
        report["passed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        _write_json_report(report)
        raise
    _write_json_report(report)
    return report


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def staging_services():
    """Gate the suite behind live Redis + PostgreSQL."""
    if not await _services_ready():
        pytest.skip("Staging services not available")


# ── Test Scenarios ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recovery_planned_restart(staging_services):
    """B-6/E-2 Scenario 1: Planned restart (no container kill)."""
    report = await _run_scenario(scenario="planned_restart", kill_redis=False, kill_pg=False)
    assert report["passed"] is True
    assert report["elapsed_s"] < 30.0, "Planned restart exceeded the 30s B-5 budget"


@pytest.mark.asyncio
async def test_recovery_redis_crash(staging_services):
    """B-6/E-2 Scenario 2: Redis crash and restart (PG snapshot must carry)."""
    report = await _run_scenario(
        scenario="redis_crash",
        kill_redis=True,
        kill_pg=False,
        reset_redis_after_restart=True,
    )
    assert report["passed"] is True
    assert report["pg_checkpoints_recovered"] >= 1
    assert report["data_loss_s"] <= 5.0, f"Data loss {report['data_loss_s']}s > 5s budget"


@pytest.mark.asyncio
async def test_recovery_pg_crash(staging_services):
    """B-6/E-2 Scenario 3: PostgreSQL crash and restart."""
    report = await _run_scenario(scenario="pg_crash", kill_redis=False, kill_pg=True)
    assert report["passed"] is True
    assert report["data_loss_s"] <= 5.0, f"Data loss {report['data_loss_s']}s > 5s budget"


@pytest.mark.asyncio
async def test_recovery_simultaneous_crash(staging_services):
    """B-6/E-2 Scenario 4: Simultaneous Redis+PG crash and restart."""
    report = await _run_scenario(
        scenario="simultaneous_crash",
        kill_redis=True,
        kill_pg=True,
        reset_redis_after_restart=True,
    )
    assert report["passed"] is True
    assert report["data_loss_s"] <= 5.0, f"Data loss {report['data_loss_s']}s > 5s budget"


@pytest.mark.asyncio
async def test_recovery_multiple_threads(staging_services):
    """Additional test: Recovery with multiple concurrent threads."""
    report = await _run_scenario(
        scenario="multiple_threads",
        kill_redis=True,
        kill_pg=True,
        threads=5,
        samples=5,
        reset_redis_after_restart=True,
    )
    assert report["passed"] is True


# ── Performance Test ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recovery_performance(staging_services):
    """B-6/E-2: Measure recovery time under load (100 checkpoints)."""
    report = await _run_scenario(
        scenario="performance",
        kill_redis=True,
        kill_pg=True,
        threads=1,
        samples=100,
        reset_redis_after_restart=True,
    )
    assert report["passed"] is True
    assert report["elapsed_s"] < 30.0, f"Recovery took {report['elapsed_s']:.1f}s, budget is 30s"

    # Stdout metric line for prometheus textfile / CI log parsing (E-2 reporting).
    print(f"[checkpoint-recovery] {json.dumps(report, sort_keys=True)}")
