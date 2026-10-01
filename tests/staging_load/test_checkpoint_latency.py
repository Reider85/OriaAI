"""B-6: checkpoint latency end-to-end < 2 ms @ p99 (ADR-010, ROADMAP §6.3).

Staging-load test: parallel LLM sessions, each writing checkpoints during node
iterations, and measure the checkpoint-write latency from aput() call completion.
Uses real RedisPostgresCheckpointer against staging Redis DB 1 and PostgreSQL.

Fixtures are function-scoped: pytest-asyncio's default loop scope is function, and
crossing loop scopes between an async fixture and the test hangs (redis async
background tasks are loop-bound).

The whole suite is gated behind RUN_STAGING_LOAD=1 (see conftest.py). The load
model follows the B-6 spec: sessions start at a steady RPS (10), each writes
checkpoints for 30-60 sec (5-10 nodes). Latency is measured per checkpoint write.
Sizes are env-tunable so a fast local smoke run is possible:
    CHECKPOINT_LATENCY_SAMPLES   (default 1000 — DoD-mandated for p99 statistics)
    CHECKPOINT_SESSIONS_CONCURRENT(default 50 — staging load, B-6 spec)
    CHECKPOINT_SESSION_START_RPS  (default 10 — new sessions per second, B-6 spec)
    CHECKPOINT_NODES_PER_SESSION  (default 10 — nodes per session)
    CHECKPOINT_NODE_DELAY_S       (default 0.1 — delay between nodes)
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
import httpx
import pytest
import redis.asyncio as aioredis
from fastapi import FastAPI

from llm_client.config import Settings
from llm_client.orchestration.checkpointers.composite import RedisPostgresCheckpointer
from llm_client.orchestration.checkpointers.factory import build_checkpointer

pytestmark = [pytest.mark.staging_load]

SAMPLE_TARGET = int(os.getenv("CHECKPOINT_LATENCY_SAMPLES", "1000"))
SESSIONS_CONCURRENT = int(os.getenv("CHECKPOINT_SESSIONS_CONCURRENT", "50"))
SESSION_START_RPS = float(os.getenv("CHECKPOINT_SESSION_START_RPS", "10"))
NODES_PER_SESSION = int(os.getenv("CHECKPOINT_NODES_PER_SESSION", "10"))
NODE_DELAY_S = float(os.getenv("CHECKPOINT_NODE_DELAY_S", "0.1"))
P99_BUDGET_MS = float(os.getenv("P99_BUDGET_MS", "2.0"))


@dataclass
class TestHandle:
    checkpointer: RedisPostgresCheckpointer
    http: httpx.AsyncClient


def _build_app(checkpointer):
    """A minimal ADR-010 app: create session + simulate graph node execution.

    The endpoint simulates a LangGraph node loop that writes checkpoints between
    nodes exactly as ADR-010 requires.
    """

    app = FastAPI(title="B-6 checkpoint latency app")

    @app.post("/sessions")
    async def create_session() -> dict:
        session_id = f"b6-{uuid.uuid4().hex[:12]}"
        return {"session_id": session_id}

    @app.post("/sessions/{session_id}/nodes")
    async def simulate_node(session_id: str) -> dict:
        """Simulate a node execution with checkpoint write."""
        thread_id = f"b6-{session_id}"

        # Simulate checkpoint data for this node
        checkpoint = {
            "id": str(uuid.uuid4()),
            "ts": time.time(),
            "channel_values": {"messages": [f"node_{session_id}"]},
            "channel_versions": {},
            "versions_seen": {},
            "updated_channels": [],
        }

        config = {"configurable": {"thread_id": thread_id}}

        # Write checkpoint and measure latency
        start_time = time.perf_counter()
        await checkpointer.aput(config, checkpoint, {"node": "simulated"})
        latency_ms = (time.perf_counter() - start_time) * 1000

        return {"latency_ms": latency_ms, "checkpoint_id": checkpoint["id"]}

    return app


@pytest.fixture
async def test_handle():
    """Setup real RedisPostgresCheckpointer and test app."""
    # Check if services are available
    try:
        # Test Redis DB 1 (checkpoint DB)
        redis_client = aioredis.from_url("redis://127.0.0.1:6379/1", decode_responses=False)
        await redis_client.ping()
        await redis_client.aclose()

        # Test PostgreSQL
        conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5434/llm_client")
        await conn.close()
    except (ConnectionError, TimeoutError):
        pytest.skip("Staging services not available")

    # Build composite checkpointer
    settings = Settings()
    settings.checkpoint_backend = "redis_postgres"
    settings.redis_checkpoint_url = "redis://127.0.0.1:6379/1"
    settings.database_url = "postgresql+asyncpg://postgres:postgres@localhost:5434/llm_client"
    settings.redis_checkpoint_ttl_seconds = 86400
    settings.checkpoint_flush_interval_seconds = 5
    settings.checkpoint_flush_batch_size = 50

    bundle = build_checkpointer(settings)
    if not bundle.checkpointer:
        pytest.skip("Could not build RedisPostgresCheckpointer")

    try:
        # Build FastAPI app with the checkpointer
        app = _build_app(bundle.checkpointer)
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0)

        yield TestHandle(checkpointer=bundle.checkpointer, http=client)
    finally:
        await client.aclose()


async def _run_session(handle: TestHandle, session_id: str) -> list[float]:
    """One session: create → simulate N nodes → collect latencies."""
    latencies = []

    # Simulate N nodes for this session
    for node_num in range(NODES_PER_SESSION):
        await asyncio.sleep(NODE_DELAY_S)  # Simulate work between nodes

        resp = await handle.http.post(f"/sessions/{session_id}/nodes")
        if resp.status_code != 200:
            return []  # Session failed

        result = resp.json()
        latencies.append(result["latency_ms"])

    return latencies


def _percentile(latencies: list[float], percentile: float) -> float:
    if not latencies:
        return float("inf")
    ordered = sorted(latencies)
    idx = max(0, min(len(ordered) - 1, round(len(ordered) * percentile) - 1))
    return ordered[idx]


@pytest.mark.asyncio
async def test_checkpoint_latency_p99_below_2ms(test_handle):
    samples: list[float] = []
    errors: list[str] = []
    spawned = 0
    inter_start_s = 1.0 / SESSION_START_RPS
    sem = asyncio.Semaphore(SESSIONS_CONCURRENT)
    started_at = time.monotonic()

    async def _paced_runner() -> None:
        # Pace CREATION at START_RPS; cap concurrent sessions via the semaphore.
        # This keeps session starts staggered instead of burst-firing,
        # matching the B-6 staging load model (10 RPS new sessions).
        nonlocal spawned
        while len(samples) < SAMPLE_TARGET:
            await sem.acquire()
            spawned += 1
            session_id = f"b6-{uuid.uuid4().hex[:12]}"
            asyncio.create_task(_run(session_id))
            next_at = time.monotonic() + inter_start_s
            delay = next_at - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)

    async def _run(session_id: str) -> None:
        try:
            result = await _run_session(test_handle, session_id)
        except Exception:  # noqa: BLE001 — any failure becomes a sample error
            result = []
        finally:
            sem.release()
        if result:
            samples.extend(result)
        else:
            errors.append("session failed")

    asyncio.create_task(_paced_runner())
    while len(samples) < SAMPLE_TARGET:
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.2)  # let in-flight sessions settle into the report

    assert samples, f"no latency samples collected (errors: {errors[:5]}, spawned={spawned})"
    p50 = _percentile(samples, 0.50)
    p95 = _percentile(samples, 0.95)
    p99 = _percentile(samples, 0.99)

    # Report shape for CI artifacts (B-6 DoD: p50/p95/p99 reported).
    report = {
        "date": datetime.now(UTC).isoformat(),
        "samples": len(samples),
        "spawned": spawned,
        "load": {"concurrent": SESSIONS_CONCURRENT, "start_rps": SESSION_START_RPS},
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "errors": len(errors),
        "budget_ms": P99_BUDGET_MS,
        "wall_s": round(time.monotonic() - started_at, 1),
    }
    print(f"[checkpoint-latency] {json.dumps(report, sort_keys=True)}")

    # Save report to file for trend tracking
    os.makedirs("reports", exist_ok=True)
    report_file = f"reports/checkpoint_latency_{datetime.now(UTC).strftime('%Y-%m-%d')}.json"

    def _write_report():
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    await asyncio.to_thread(_write_report)

    assert p99 < P99_BUDGET_MS, (
        f"checkpoint p99 latency {p99:.2f} ms exceeds the {P99_BUDGET_MS:.0f} ms budget "
        f"(p50={p50:.2f} ms, {len(samples)} samples, {len(errors)} errored rounds)"
    )
