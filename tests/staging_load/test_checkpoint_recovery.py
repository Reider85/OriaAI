"""B-6: checkpoint recovery integration tests (4 scenarios).

Integration tests for the B-5 recovery protocol against real Redis + PostgreSQL.
Covers the four restart/failure scenarios from the B-6 spec. Every test skips
when the backing services are not reachable, so the suite stays green on a
laptop with nothing but docker-compose down.

Scenarios are reproduced by killing the Docker containers (SIGKILL) and restarting,
which simulates process failure. Real process restart is simulated by creating
a new RedisPostgresCheckpointer instance.

Uses subprocess.run for docker commands (per B-6 guidance).
"""

import asyncio
import json
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import redis.asyncio as aioredis

from llm_client.config import Settings
from llm_client.orchestration.checkpointers.composite import RedisPostgresCheckpointer
from llm_client.orchestration.checkpointers.factory import build_checkpointer

pytestmark = [pytest.mark.staging_load]

REDIS_URL = "redis://127.0.0.1:6379/1"
PG_DSN = "postgresql://postgres:postgres@localhost:5432/llm_client"
CONTAINER_NAMES = ["llm-redis", "llm-postgres"]

AGENT_CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    thread_id UUID NOT NULL,
    checkpoint_id UUID NOT NULL,
    parent_id UUID,
    state JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
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
    try:
        # Test Redis DB 1
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
        await redis_client.ping()
        await redis_client.aclose()
        redis_ok = True
    except (ConnectionError, TimeoutError):
        redis_ok = False
    
    try:
        # Test PostgreSQL
        conn = await asyncpg.connect(PG_DSN)
        await conn.close()
        pg_ok = True
    except (ConnectionError, TimeoutError):
        pg_ok = False
    
    return redis_ok and pg_ok


def _kill_container(container_name: str) -> None:
    """Kill a Docker container with SIGKILL."""
    try:
        subprocess.run(
            ["docker", "kill", container_name],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"Failed to kill {container_name}: {exc}")


def _restart_container(container_name: str) -> None:
    """Restart a Docker container."""
    try:
        subprocess.run(
            ["docker", "restart", container_name],
            check=True,
            capture_output=True,
            timeout=30,
        )
        # Wait for health check
        time.sleep(5)
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"Failed to restart {container_name}: {exc}")


def _build_checkpointer() -> RedisPostgresCheckpointer:
    """Build a fresh RedisPostgresCheckpointer (simulates process restart)."""
    settings = Settings()
    settings.checkpoint_backend = "redis_postgres"
    settings.redis_checkpoint_url = REDIS_URL
    settings.database_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/llm_client"
    settings.redis_checkpoint_ttl_seconds = 86400
    settings.checkpoint_flush_interval_seconds = 5
    settings.checkpoint_flush_batch_size = 50
    
    bundle = build_checkpointer(settings)
    if not bundle.checkpointer or not isinstance(bundle.checkpointer, RedisPostgresCheckpointer):
        pytest.fail("Could not build RedisPostgresCheckpointer")
    
    return bundle.checkpointer


async def _write_checkpoints(checkpointer: RedisPostgresCheckpointer, thread_id: str, count: int = 10):
    """Write N checkpoints for a thread."""
    checkpoints = []
    for i in range(count):
        checkpoint = make_checkpoint(i * 0.1)  # 0.1s apart
        config = config_for(thread_id)
        await checkpointer.aput(config, checkpoint, {"node": f"node_{i}"})
        checkpoints.append(checkpoint)
    return checkpoints


async def _verify_recovery(checkpointer: RedisPostgresCheckpointer, thread_id: str, original_checkpoints: list):
    """Verify that recovery restored all checkpoints."""
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


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def checkpointer():
    """Setup RedisPostgresCheckpointer."""
    if not await _services_ready():
        pytest.skip("Staging services not available")
    
    return _build_checkpointer()


@pytest.fixture
def thread_id():
    """Generate a unique thread_id for each test."""
    return f"b6-recovery-{uuid.uuid4().hex[:8]}"


# ── Test Scenarios ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recovery_planned_restart(checkpointer, thread_id):
    """B-6 Scenario 1: Planned restart (no container kill)."""
    # Write 10 checkpoints
    original_checkpoints = await _write_checkpoints(checkpointer, thread_id, 10)
    
    # Simulate planned restart by creating new checkpointer
    new_checkpointer = _build_checkpointer()
    
    # Verify recovery
    await _verify_recovery(new_checkpointer, thread_id, original_checkpoints)


@pytest.mark.asyncio
async def test_recovery_redis_crash(checkpointer, thread_id):
    """B-6 Scenario 2: Redis crash and restart."""
    # Write 10 checkpoints
    original_checkpoints = await _write_checkpoints(checkpointer, thread_id, 10)
    
    # Kill Redis container
    _kill_container("llm-redis")
    
    # Wait a bit for any pending operations
    await asyncio.sleep(1)
    
    # Restart Redis
    _restart_container("llm-redis")
    
    # Simulate process restart with new checkpointer
    new_checkpointer = _build_checkpointer()
    
    # Verify recovery
    await _verify_recovery(new_checkpointer, thread_id, original_checkpoints)


@pytest.mark.asyncio
async def test_recovery_pg_crash(checkpointer, thread_id):
    """B-6 Scenario 3: PostgreSQL crash and restart."""
    # Write 10 checkpoints
    original_checkpoints = await _write_checkpoints(checkpointer, thread_id, 10)
    
    # Kill PostgreSQL container
    _kill_container("llm-postgres")
    
    # Wait a bit for any pending operations
    await asyncio.sleep(1)
    
    # Restart PostgreSQL
    _restart_container("llm-postgres")
    
    # Simulate process restart with new checkpointer
    new_checkpointer = _build_checkpointer()
    
    # Verify recovery
    await _verify_recovery(new_checkpointer, thread_id, original_checkpoints)


@pytest.mark.asyncio
async def test_recovery_simultaneous_crash(checkpointer, thread_id):
    """B-6 Scenario 4: Simultaneous Redis+PG crash and restart."""
    # Write 10 checkpoints
    original_checkpoints = await _write_checkpoints(checkpointer, thread_id, 10)
    
    # Kill both containers simultaneously
    _kill_container("llm-redis")
    _kill_container("llm-postgres")
    
    # Wait a bit for any pending operations
    await asyncio.sleep(1)
    
    # Restart both containers
    _restart_container("llm-redis")
    _restart_container("llm-postgres")
    
    # Simulate process restart with new checkpointer
    new_checkpointer = _build_checkpointer()
    
    # Verify recovery
    await _verify_recovery(new_checkpointer, thread_id, original_checkpoints)


@pytest.mark.asyncio
async def test_recovery_multiple_threads(checkpointer):
    """Additional test: Recovery with multiple concurrent threads."""
    thread_ids = [f"b6-multi-{i}" for i in range(5)]
    
    # Write checkpoints for multiple threads
    original_data = {}
    for thread_id in thread_ids:
        checkpoints = await _write_checkpoints(checkpointer, thread_id, 5)
        original_data[thread_id] = checkpoints
    
    # Simulate simultaneous crash and restart
    _kill_container("llm-redis")
    _kill_container("llm-postgres")
    await asyncio.sleep(1)
    _restart_container("llm-redis")
    _restart_container("llm-postgres")
    
    # Verify recovery for all threads
    new_checkpointer = _build_checkpointer()
    for thread_id in thread_ids:
        await _verify_recovery(new_checkpointer, thread_id, original_data[thread_id])


# ── Performance Test ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recovery_performance(checkpointer, thread_id):
    """B-6: Measure recovery time under load."""
    # Write 100 checkpoints
    original_checkpoints = await _write_checkpoints(checkpointer, thread_id, 100)
    
    # Simulate crash and restart
    _kill_container("llm-redis")
    _kill_container("llm-postgres")
    await asyncio.sleep(1)
    _restart_container("llm-redis")
    _restart_container("llm-postgres")
    
    # Measure recovery time
    start_time = time.perf_counter()
    new_checkpointer = _build_checkpointer()
    await _verify_recovery(new_checkpointer, thread_id, original_checkpoints)
    recovery_time = time.perf_counter() - start_time
    
    # Recovery should be < 30 seconds (B-5 budget)
    assert recovery_time < 30.0, f"Recovery took {recovery_time:.1f}s, budget is 30s"
    
    # Report for CI
    report = {
        "recovery_time_s": round(recovery_time, 2),
        "checkpoints_count": len(original_checkpoints),
        "budget_s": 30.0,
    }
    print(f"[checkpoint-recovery] {json.dumps(report, sort_keys=True)}")