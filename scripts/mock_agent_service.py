#!/usr/bin/env python
"""Mock agent-service for UI latency benchmarking (prompt 11).

DEPRECATED: Phase 1 AG-0 replaces this with the real agent-service
(src/llm_client/agent/service.py).  This mock is kept exclusively for the
UI latency benchmark (prompt 11 UI-PROMPTS) where a deterministic 50 ms
per-1000-token delay is needed.  Do NOT use as the main backend.

Spins up a minimal FastAPI server that mimics the real agent-service SSE
endpoints (POST /sessions/{id}/chat, GET /sessions/{id}/stream).  The mock
emits exactly TOKEN_COUNT tokens with TOKEN_DELAY_MS between each so the
benchmark can measure UI rendering performance deterministically.

Usage::

    python scripts/mock_agent_service.py              # default :8000
    python scripts/mock_agent_service.py --port 8001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

TOKEN_COUNT = int(os.getenv("MOCK_TOKEN_COUNT", "1000"))
TOKEN_DELAY_MS = float(os.getenv("MOCK_TOKEN_DELAY_MS", "50"))
TOKEN_TEXT = "Hello, this is a simulated token from the mock agent-service. "

app = FastAPI(title="Mock Agent Service", version="0.1.0")

_sessions: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


@app.post("/sessions/{session_id}/chat")
async def start_chat(session_id: str, body: dict[str, Any]) -> dict[str, str]:
    with _lock:
        _sessions[session_id] = {
            "started": time.monotonic(),
            "prompt": body.get("message", ""),
        }
    return {"status": "ok", "session_id": session_id}


@app.get("/sessions/{session_id}/stream")
async def stream_tokens(session_id: str) -> StreamingResponse:
    async def _generate():
        delay_s = TOKEN_DELAY_MS / 1000.0
        for i in range(TOKEN_COUNT):
            token = f"token-{i} "
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n"
            await asyncio.sleep(delay_s)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MOCK_PORT", "8000")),
    )
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(
        f"Mock agent-service starting on {args.host}:{args.port} "
        f"(tokens={TOKEN_COUNT}, delay={TOKEN_DELAY_MS}ms)",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
