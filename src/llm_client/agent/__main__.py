"""Entry point for ``python -m llm_client.agent``.

Reads AGENT_SERVICE_PORT from env (default 8000) and starts the agent-service
FastAPI application via uvicorn.
"""

import os

import uvicorn

from .service import app

if __name__ == "__main__":
    port = int(os.getenv("AGENT_SERVICE_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
