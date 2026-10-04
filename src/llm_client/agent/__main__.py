"""Entry point for ``python -m llm_client.agent``.

Reads AGENT_SERVICE_PORT and AGENT_SERVICE_HOST from env and starts the
agent-service FastAPI application via uvicorn.

Docker port publishing requires the app to listen on 0.0.0.0 inside the
container; compose already binds the host port to 127.0.0.1 only.
"""

import os

import uvicorn

from .service import app

if __name__ == "__main__":
    host = os.getenv("AGENT_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_SERVICE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
