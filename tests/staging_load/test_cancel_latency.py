"""F-1: cancel latency end-to-end < 100 ms @ p99 (ADR-013, ROADMAP §5.6 p.1).

Staging-load test: parallel LLM sessions, cancel each after a short delay, and
measure the end-to-end latency from POST /sessions/{id}/cancel until the SSE stream
actually stops (last chunk). Uses real Redis pub/sub, the real CancelEndpoint /
CancelPublisher / CancelSubscriber / CancellationToken; the "graph" is a simulated
LangGraph node loop that only checks the token BETWEEN nodes — the ADR-013 contract.

Fixtures are function-scoped: pytest-asyncio's default loop scope is function, and
crossing loop scopes between an async fixture and the test hangs (redis async
background tasks are loop-bound).

The whole suite is gated behind RUN_STAGING_LOAD=1 (see conftest.py). The load
model follows the F-1 spec: sessions start at a steady RPS (10), each is cancelled
5 s after ITS OWN start, so at any moment ~50 sessions stream concurrently. Cancels
are staggered (~10/s) — never a same-instant burst, which would pile concurrent
redis PUBLISH commands onto one asyncio loop and measure a client artifact, not the
cancel mechanism. Sizes are env-tunable so a fast local smoke run is possible:
    CANCEL_LATENCY_SAMPLES    (default 1000 — DoD-mandated for p99 statistics)
    CANCEL_SESSIONS_CONCURRENT(default 50 — staging load, F-1 spec)
    CANCEL_SESSION_START_RPS  (default 10 — new sessions per second, F-1 spec)
    CANCEL_SESSION_DELAY_S    (default 5 s — cancel 5 s after start, F-1 spec)
    CANCEL_NODE_CADENCE_S     (default 0.005 — token-stream cadence; the graph checks
                               the token continuously, as the cancellable LLM call
                               does via the on_cancel callback, ADR-013/C-1)
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from redis import asyncio as aioredis

from llm_client.transport.cancel import CancellationTokenRegistry
from llm_client.transport.endpoint import SessionState, build_cancel_router
from llm_client.transport.publisher import CancelPublisher
from llm_client.transport.subscriber import CancelSubscriber

pytestmark = [pytest.mark.staging_load]

SAMPLE_TARGET = int(os.getenv("CANCEL_LATENCY_SAMPLES", "1000"))
SESSIONS_CONCURRENT = int(os.getenv("CANCEL_SESSIONS_CONCURRENT", "50"))
SESSION_START_RPS = float(os.getenv("CANCEL_SESSION_START_RPS", "10"))
SESSION_DELAY_S = float(os.getenv("CANCEL_SESSION_DELAY_S", "5"))
NODE_CADENCE_S = float(os.getenv("CANCEL_NODE_CADENCE_S", "0.005"))
P99_BUDGET_MS = 100.0


@dataclass
class AppHandle:
    http: httpx.AsyncClient
    registry: CancellationTokenRegistry
    subscriber: CancelSubscriber


class _LastChunk:
    """Records when the final SSE chunk arrives for a session."""

    def __init__(self) -> None:
        self.monotonic = 0.0
        self.payload = ""

    @property
    def done(self) -> bool:
        return self.monotonic > 0


def _build_app(redis_client):
    """A minimal ADR-013 app: create session + SSE stream + cancel endpoint.

    The stream endpoint stands in for the LangGraph SSE data-plane; it checks the
    per-session CancellationToken between "nodes" exactly as ADR-013 requires.
    """
    registry = CancellationTokenRegistry()
    state = SessionState()
    subscriber = CancelSubscriber(redis_client, registry)
    publisher = CancelPublisher(redis_client)

    app = FastAPI(title="F-1 cancel latency app")

    @app.post("/sessions")
    async def create_session() -> dict:
        session_id = f"f1-{uuid.uuid4().hex[:12]}"
        registry.register(session_id)
        state.activate(session_id)
        await subscriber.subscribe(session_id)
        return {"session_id": session_id}

    @app.get("/sessions/{session_id}/stream")
    async def stream_session(session_id: str) -> StreamingResponse:
        token = registry.get(session_id)
        if token is None:
            raise HTTPException(status_code=404, detail="Session not found")

        async def _feed():
            i = 0
            # Simulated LangGraph node loop. Only checks the token BETWEEN nodes.
            while not token.is_cancelled and i < 1_000_000:
                yield f"data: {json.dumps({'chunk': i, 'session_id': session_id})}\n\n"
                i += 1
                await asyncio.sleep(NODE_CADENCE_S)
            # Trailer: partial answer when cancelled, DONE when the graph finished.
            if token.is_cancelled:
                yield (
                    f"data: {json.dumps({'final': 'partial_answer', 'session_id': session_id})}\n\n"
                )
            else:
                yield f"data: {json.dumps({'final': 'done', 'session_id': session_id})}\n\n"

        return StreamingResponse(_feed(), media_type="text/event-stream")

    app.include_router(build_cancel_router(publisher, state))
    return app, registry, subscriber


@pytest.fixture
async def app_handle():
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6380/0")
    redis_client = aioredis.from_url(url, decode_responses=True)
    try:
        await redis_client.ping()
    except Exception as exc:  # noqa: BLE001 — probe anything that could mean Redis is down
        pytest.skip(f"Redis not available at {url}: {exc}")

    app, registry, subscriber = _build_app(redis_client)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0)
    try:
        yield AppHandle(http=client, registry=registry, subscriber=subscriber)
    finally:
        await client.aclose()
        await redis_client.aclose()


async def _run_session(handle: AppHandle, *, session_delay_s: float) -> dict:
    """One end-to-end session: create → stream → cancel → measure stop latency."""
    created = await handle.http.post("/sessions")
    assert created.status_code == 200, created.text
    session_id = created.json()["session_id"]

    last = _LastChunk()

    async def consume_stream() -> None:
        async with handle.http.stream("GET", f"/sessions/{session_id}/stream") as resp:
            async for chunk in resp.aiter_bytes():
                if chunk:
                    last.monotonic = time.monotonic()
                    last.payload = chunk.decode("utf-8", errors="replace")

    stream_task = asyncio.create_task(consume_stream())
    await asyncio.sleep(session_delay_s)

    send_at = time.monotonic()
    cancel_resp = await handle.http.post(
        f"/sessions/{session_id}/cancel",
        json={"reason": "user_cancelled", "user_id": "f1-load"},
    )
    cancelled_http_ms = (time.monotonic() - send_at) * 1000
    try:
        if cancel_resp.status_code != 202:
            stream_task.cancel()
            return {
                "ok": False,
                "error": f"cancel returned {cancel_resp.status_code}: {cancel_resp.text}",
            }
        await stream_task
    except Exception as exc:  # noqa: BLE001 — surface stream failure as a sample error
        return {"ok": False, "error": f"session {session_id} failed: {exc}"}
    finally:
        await handle.subscriber.unsubscribe(session_id)
        handle.registry.cleanup(session_id)

    stop_at = last.monotonic
    if not last.done or stop_at < send_at:
        return {
            "ok": False,
            "error": f"no SSE chunk after cancel for {session_id} (last={last.monotonic:.3f}, sent={send_at:.3f})",
        }
    latency_ms = (stop_at - send_at) * 1000
    return {
        "ok": True,
        "latency_ms": latency_ms,
        "cancel_http_ms": cancelled_http_ms,
        "partial_answer": '"final": "partial_answer"' in last.payload,
    }


def _percentile(latencies: list[float], percentile: float) -> float:
    if not latencies:
        return float("inf")
    ordered = sorted(latencies)
    idx = max(0, min(len(ordered) - 1, round(len(ordered) * percentile) - 1))
    return ordered[idx]


@pytest.mark.asyncio
async def test_cancel_latency_p99_below_100ms(app_handle):
    samples: list[float] = []
    errors: list[str] = []
    spawned = 0
    inter_start_s = 1.0 / SESSION_START_RPS
    sem = asyncio.Semaphore(SESSIONS_CONCURRENT)
    started_at = time.monotonic()

    async def _paced_runner() -> None:
        # Pace CREATION at START_RPS; cap concurrent sessions via the semaphore.
        # This keeps session starts (and therefore cancels) staggered instead of
        # burst-firing, matching the F-1 staging load model (10 RPS new sessions).
        nonlocal spawned
        while len(samples) < SAMPLE_TARGET:
            await sem.acquire()
            spawned += 1
            asyncio.create_task(_run())
            next_at = time.monotonic() + inter_start_s
            delay = next_at - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)

    async def _run() -> None:
        try:
            result = await _run_session(app_handle, session_delay_s=SESSION_DELAY_S)
        except Exception as exc:  # noqa: BLE001 — any failure becomes a sample error
            result = {"ok": False, "error": f"session failed: {exc}"}
        finally:
            sem.release()
        if result["ok"]:
            samples.append(result["latency_ms"])
        else:
            errors.append(result["error"])

    asyncio.create_task(_paced_runner())
    while len(samples) < SAMPLE_TARGET:
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.2)  # let in-flight sessions settle into the report

    assert samples, f"no latency samples collected (errors: {errors[:5]}, spawned={spawned})"
    p50 = _percentile(samples, 0.50)
    p95 = _percentile(samples, 0.95)
    p99 = _percentile(samples, 0.99)

    # Report shape for CI artifacts (F-1 DoD: p50/p95/p99 reported).
    report = {
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
    print(f"[cancel-latency] {json.dumps(report, sort_keys=True)}")

    assert p99 < P99_BUDGET_MS, (
        f"cancel p99 latency {p99:.2f} ms exceeds the {P99_BUDGET_MS:.0f} ms budget "
        f"(p50={p50:.2f} ms, {len(samples)} samples, {len(errors)} errored rounds)"
    )


@pytest.mark.asyncio
async def test_cancel_returns_partial_answer(app_handle):
    """F-1 DoD: partial answer must be returned in 100% of cancelled sessions."""
    passed = 0
    attempts = 12
    diagnostics: list[str] = []
    for _ in range(attempts):
        result = await _run_session(app_handle, session_delay_s=0.1)
        if result["ok"] and result["partial_answer"]:
            passed += 1
        else:
            diagnostics.append(
                f"ok={result['ok']} partial={result.get('partial_answer')} err={result.get('error')}"
            )
    if diagnostics:
        print(f"[cancel-latency] partial-answer diagnostics: {diagnostics[:4]}")
    assert passed == attempts, (
        f"partial answer returned only in {passed}/{attempts} cancelled sessions"
    )
