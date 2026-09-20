"""Minimal FastAPI application wiring the ADR-013 cancel control-plane (B-1)."""
import logging

from fastapi import FastAPI
from redis import asyncio as aioredis

from .transport.cancel import CancellationTokenRegistry
from .transport.endpoint import build_cancel_router, get_session_state
from .transport.publisher import CancelPublisher
from .transport.subscriber import CancelSubscriber

logger = logging.getLogger(__name__)


def create_app(redis_url: str | None = None) -> FastAPI:
    """Create the FastAPI app with the cancel endpoint wired to Redis pub/sub."""
    from .config import settings

    redis_url = redis_url or settings.redis_url
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    registry = CancellationTokenRegistry()
    publisher = CancelPublisher(redis_client)
    state = get_session_state()

    app = FastAPI(title="LLM Client — ADR-013 control-plane", version="0.1.0")
    app.state.redis = redis_client
    app.state.registry = registry
    app.state.subscriber = CancelSubscriber(redis_client, registry)

    @app.on_event("startup")
    async def _startup() -> None:
        await redis_client.ping()
        logger.info("Redis connection OK at %s", redis_url)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await app.state.subscriber.unsubscribe_all()
        await redis_client.aclose()

    app.include_router(build_cancel_router(publisher, state))
    return app


__all__ = ["create_app"]