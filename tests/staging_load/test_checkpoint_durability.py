"""B-6: checkpoint durability 7-day pilot week simulation.

Simulates 7 days of checkpoint operations with fast-forward time acceleration
to test durability under realistic load patterns. Uses real RedisPostgresCheckpointer
against staging Redis DB 1 and PostgreSQL.

The simulation runs at DURABILITY_SPEEDUP speed (default 100x = ~100 minutes real time
for 7 simulated days). Periodic events test recovery:

- Every 5 simulated hours: planned app restart
- Every 24 simulated hours: Redis restart
- At end: simultaneous Redis+PG crash and recovery

Durability is measured as (checkpoints retrievable after recovery) / (total written).
PASS criterion: durability ≥ 99.9%.

Gated behind RUN_STAGING_LOAD=1 (see conftest.py).
"""

import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
import redis.asyncio as aioredis

from llm_client.config import Settings
from llm_client.orchestration.checkpointers.composite import RedisPostgresCheckpointer
from llm_client.orchestration.checkpointers.factory import build_checkpointer

pytestmark = [pytest.mark.staging_load]

# Configuration
SPEEDUP = float(os.getenv("DURABILITY_SPEEDUP", "100"))  # 100x default = ~100 min real time
SIMULATED_DAYS = 7
SIMULATED_HOURS_PER_DAY = 24
SIMULATED_MINUTES_PER_HOUR = 60
SIMULATED_SECONDS_PER_MINUTE = 60

# Derived timing (in real seconds)
REAL_SECONDS_PER_SIMULATED_HOUR = (3600 / SPEEDUP)  # 3600s / 100 = 36s
REAL_SECONDS_PER_SIMULATED_DAY = REAL_SECONDS_PER_SIMULATED_HOUR * SIMULATED_HOURS_PER_DAY  # 864s
REAL_SECONDS_PER_SIMULATED_WEEK = REAL_SECONDS_PER_SIMULATED_DAY * SIMULATED_DAYS  # 6048s

# Event timing
PLANNED_RESTART_INTERVAL_SIM_HOURS = 5  # Every 5 simulated hours
REDIS_RESTART_INTERVAL_SIM_HOURS = 24   # Every 24 simulated hours
CHECKPOINTS_PER_SESSION = 10
SESSIONS_COUNT = 1000
TOTAL_CHECKPOINTS = SESSIONS_COUNT * CHECKPOINTS_PER_SESSION

# Services
REDIS_URL = "redis://127.0.0.1:6379/1"
PG_DSN = "postgresql://postgres:postgres@localhost:5434/llm_client"
CONTAINER_NAMES = ["llm-redis", "llm-postgres"]


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_checkpoint(session_id: str, node_num: int) -> dict:
    """Create a checkpoint for a session node."""
    ts = datetime.now(UTC)
    return {
        "id": str(uuid.uuid4()),
        "ts": ts.isoformat(),
        "channel_values": {"messages": [f"session_{session_id}_node_{node_num}"]},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": [],
    }


def config_for(session_id: str) -> dict:
    return {"configurable": {"thread_id": f"b6-dur-{session_id}"}}


async def _services_ready() -> bool:
    """Check if Redis and PostgreSQL are available."""
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
        await redis_client.ping()
        await redis_client.aclose()
        redis_ok = True
    except (ConnectionError, TimeoutError):
        redis_ok = False
    
    try:
        conn = await asyncpg.connect(PG_DSN)
        await conn.close()
        pg_ok = True
    except (ConnectionError, TimeoutError):
        pg_ok = False
    
    return redis_ok and pg_ok


def _kill_container(container_name: str) -> None:
    """Kill a Docker container with SIGKILL."""
    try:
        import subprocess
        subprocess.run(
            ["docker", "kill", container_name],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to kill {container_name}: {exc}")


def _restart_container(container_name: str) -> None:
    """Restart a Docker container."""
    try:
        import subprocess
        subprocess.run(
            ["docker", "restart", container_name],
            check=True,
            capture_output=True,
            timeout=30,
        )
        # Wait for health check
        time.sleep(5)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to restart {container_name}: {exc}")


def _build_checkpointer() -> RedisPostgresCheckpointer:
    """Build a fresh RedisPostgresCheckpointer."""
    settings = Settings()
    settings.checkpoint_backend = "redis_postgres"
    settings.redis_checkpoint_url = REDIS_URL
    settings.database_url = "postgresql+asyncpg://postgres:postgres@localhost:5434/llm_client"
    settings.redis_checkpoint_ttl_seconds = 86400
    settings.checkpoint_flush_interval_seconds = 5
    settings.checkpoint_flush_batch_size = 50
    
    bundle = build_checkpointer(settings)
    if not bundle.checkpointer or not isinstance(bundle.checkpointer, RedisPostgresCheckpointer):
        raise RuntimeError("Could not build RedisPostgresCheckpointer")
    
    return bundle.checkpointer


async def _write_session_checkpoints(checkpointer: RedisPostgresCheckpointer, session_id: str) -> list[dict]:
    """Write checkpoints for a single session."""
    checkpoints = []
    config = config_for(session_id)
    
    for node_num in range(CHECKPOINTS_PER_SESSION):
        checkpoint = make_checkpoint(session_id, node_num)
        await checkpointer.aput(config, checkpoint, {"node": node_num})
        checkpoints.append(checkpoint)
        # Small delay between nodes
        await asyncio.sleep(0.01)
    
    return checkpoints


async def _verify_checkpoints(checkpointer: RedisPostgresCheckpointer, session_id: str, expected_checkpoints: list[dict]) -> bool:
    """Verify that all checkpoints for a session are retrievable."""
    config = config_for(session_id)
    
    # Get the latest checkpoint
    latest = await checkpointer.aget(config)
    if not latest:
        return False
    
    # Verify the last checkpoint matches
    expected_last = expected_checkpoints[-1]
    if latest["id"] != expected_last["id"]:
        return False
    
    # List all checkpoints and count them
    all_checkpoints = list(checkpointer.alist(config, limit=CHECKPOINTS_PER_SESSION + 1))
    return len(all_checkpoints) >= len(expected_checkpoints)


# ── Test ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkpoint_durability_7day_simulation():
    """B-6: 7-day durability simulation with fast-forward time."""
    if not await _services_ready():
        pytest.skip("Staging services not available")
    
    checkpointer = _build_checkpointer()
    
    # Track simulation state
    simulation_start = time.monotonic()
    written_sessions: dict[str, list[dict]] = {}
    lost_sessions = set()
    
    print(f"[durability] Starting 7-day simulation at {SPEEDUP}x speed")
    print(f"[durability] Expected duration: ~{REAL_SECONDS_PER_SIMULATED_WEEK:.0f}s real time")
    
    # Phase 1: Write all checkpoints (simulated sessions over time)
    for session_num in range(SESSIONS_COUNT):
        session_id = f"b6-dur-{session_num:04d}"
        
        # Write checkpoints for this session
        checkpoints = await _write_session_checkpoints(checkpointer, session_id)
        written_sessions[session_id] = checkpoints
        
        # Simulate time passing between sessions
        await asyncio.sleep(0.1)  # 100ms between sessions
        
        # Periodic progress reporting
        if session_num % 100 == 0:
            elapsed = time.monotonic() - simulation_start
            progress = session_num / SESSIONS_COUNT * 100
            print(f"[durability] Progress: {progress:.1f}% ({session_num}/{SESSIONS_COUNT} sessions, {elapsed:.1f}s elapsed)")
    
    # Phase 2: Simulate periodic events during the week
    current_sim_hours = 0
    
    while current_sim_hours < SIMULATED_DAYS * SIMULATED_HOURS_PER_DAY:
        # Check for planned restart event (every 5 simulated hours)
        if current_sim_hours % PLANNED_RESTART_INTERVAL_SIM_HOURS == 0 and current_sim_hours > 0:
            print(f"[durability] Planned restart at {current_sim_hours}h simulated")
            # Simulate app restart by creating new checkpointer
            checkpointer = _build_checkpointer()
            
            # Verify all sessions still work
            for session_id, checkpoints in written_sessions.items():
                if not await _verify_checkpoints(checkpointer, session_id, checkpoints):
                    lost_sessions.add(session_id)
                    print(f"[durability] Lost session during restart: {session_id}")
        
        # Check for Redis restart event (every 24 simulated hours)
        if current_sim_hours % REDIS_RESTART_INTERVAL_SIM_HOURS == 0 and current_sim_hours > 0:
            print(f"[durability] Redis restart at {current_sim_hours}h simulated")
            _kill_container("llm-redis")
            await asyncio.sleep(1)
            _restart_container("llm-redis")
            
            # Simulate process restart with new checkpointer
            checkpointer = _build_checkpointer()
            
            # Verify all sessions still work
            for session_id, checkpoints in written_sessions.items():
                if not await _verify_checkpoints(checkpointer, session_id, checkpoints):
                    lost_sessions.add(session_id)
                    print(f"[durability] Lost session during Redis restart: {session_id}")
        
        # Advance time (1 simulated hour)
        await asyncio.sleep(REAL_SECONDS_PER_SIMULATED_HOUR)
        current_sim_hours += 1
    
    # Phase 3: Final simultaneous crash and recovery
    print("[durability] Final simultaneous crash at end of week")
    _kill_container("llm-redis")
    _kill_container("llm-postgres")
    await asyncio.sleep(1)
    _restart_container("llm-redis")
    _restart_container("llm-postgres")
    
    # Simulate process restart with new checkpointer
    final_checkpointer = _build_checkpointer()
    
    # Final verification
    recovered_sessions = 0
    for session_id, checkpoints in written_sessions.items():
        if await _verify_checkpoints(final_checkpointer, session_id, checkpoints):
            recovered_sessions += 1
    
    # Calculate durability score
    durability_score = recovered_sessions / SESSIONS_COUNT
    
    # Report results
    elapsed = time.monotonic() - simulation_start
    report = {
        "simulated_days": SIMULATED_DAYS,
        "speedup": SPEEDUP,
        "real_time_s": round(elapsed, 1),
        "total_sessions": SESSIONS_COUNT,
        "recovered_sessions": recovered_sessions,
        "lost_sessions": len(lost_sessions),
        "durability_score": durability_score,
        "pass_threshold": 0.999,
        "budget_met": durability_score >= 0.999,
    }
    
    print(f"[durability] {json.dumps(report, sort_keys=True)}")
    
    # Assert pass criterion
    assert durability_score >= 0.999, (
        f"Durability score {durability_score:.4f} below threshold 0.999 "
        f"(recovered {recovered_sessions}/{SESSIONS_COUNT} sessions)"
    )
    
    # Additional assertions
    assert len(lost_sessions) <= SESSIONS_COUNT * 0.001, (
        f"Too many lost sessions: {len(lost_sessions)} (max allowed: {SESSIONS_COUNT * 0.001})"
    )
    assert elapsed <= REAL_SECONDS_PER_SIMULATED_WEEK * 1.5, (
        f"Test took too long: {elapsed:.1f}s (budget: {REAL_SECONDS_PER_SIMULATED_WEEK:.1f}s)"
    )


# ── Smoke Test ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkpoint_durability_smoke():
    """Quick smoke test with 10x speedup for local development."""
    original_speedup = os.environ.get("DURABILITY_SPEEDUP")
    os.environ["DURABILITY_SPEEDUP"] = "10"
    
    try:
        await test_checkpoint_durability_7day_simulation()
    finally:
        if original_speedup:
            os.environ["DURABILITY_SPEEDUP"] = original_speedup
        else:
            del os.environ["DURABILITY_SPEEDUP"]
