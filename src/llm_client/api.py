"""FastAPI application wiring the ADR-013 cancel control-plane (B-1, C-2) and the
ADR-014 dual-stream logging (D-6 dev-mode toggle).

Dev mode (default): forensic stream is off — no Vault dependency, operational logging
always enabled, PII masking always on. Staging/prod: forensic stream enabled and Vault
is mandatory (startup fails fast if unreachable).
"""
import logging

from fastapi import FastAPI
from redis import asyncio as aioredis

from .config import Settings
from .transport.cancel import CancellationTokenRegistry
from .transport.endpoint import build_cancel_router, get_session_state
from .transport.publisher import CancelPublisher
from .transport.subscriber import CancelSubscriber

logger = logging.getLogger(__name__)


def create_app(redis_url: str | None = None, _settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI app with the cancel endpoint wired to Redis pub/sub."""
    from .config import settings as default_settings

    settings = _settings or default_settings
    from .observability.forensic_writer import ForensicStreamWriter, build_forensic_writer
    from .observability.kms_provider import (
        KMSKeyProvider,
        LocalDevKeyProvider,
        VaultTransitKeyProvider,
    )
    from .observability.operational_writer import build_operational_writer
    from .security.pii_detector import PIIDetector

    redis_url = redis_url or settings.redis_url
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    registry = CancellationTokenRegistry()
    publisher = CancelPublisher(redis_client)
    state = get_session_state()

    # ── ADR-014 dual-stream logging ──────────────────────────────────────────
    pii_detector = PIIDetector(
        spacy_model=settings.pii_detector_spacy_model,
        enabled=settings.pii_detector_enabled,
    )

    forensic_writer: ForensicStreamWriter | None = None
    kms_provider: KMSKeyProvider | None = None
    if settings.forensic_stream_enabled:
        if settings.kms_provider == "vault":
            kms_provider = VaultTransitKeyProvider(
                settings.vault_addr, settings.vault_token, settings.vault_transit_key
            )
            logger.info("KMS provider: Vault transit (%s)", settings.vault_transit_key)
        else:
            kms_provider = LocalDevKeyProvider()
        from .storage.factory import create_file_storage

        forensic_writer = build_forensic_writer(
            settings,
            kms_provider,
            create_file_storage(),
        )
    else:
        logger.warning("Forensic stream disabled — dev mode")

    operational_writer = build_operational_writer(settings, pii_detector)

    async def _on_cancel_event(event: dict) -> None:
        # Operational: minimal, PII-masked. user_id never appears raw here.
        await operational_writer.write(
            {
                "event_type": event["event_type"],
                "session_id": event["session_id"],
                "user_id": "[MASKED]" if event.get("user_id") else None,
                "reason": event["reason"],
                "timestamp": event["timestamp"],
            }
        )
        # Forensic: full trace, encrypted via KMS.
        if forensic_writer is not None:
            await forensic_writer.write(event)

    subscriber = CancelSubscriber(redis_client, registry, cancel_event_handler=_on_cancel_event)

    app = FastAPI(title="LLM Client — ADR-013 control-plane", version="0.1.0")
    app.state.redis = redis_client
    app.state.registry = registry
    app.state.subscriber = subscriber
    app.state.operational_writer = operational_writer
    app.state.forensic_writer = forensic_writer
    app.state.pii_detector = pii_detector

    @app.on_event("startup")
    async def _startup() -> None:
        await redis_client.ping()
        logger.info("Redis connection OK at %s", redis_url)
        await operational_writer.start()
        if forensic_writer is not None:
            await forensic_writer.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await app.state.subscriber.unsubscribe_all()
        await operational_writer.close()
        if forensic_writer is not None:
            await forensic_writer.close()
        await redis_client.aclose()

    app.include_router(build_cancel_router(publisher, state))
    return app


__all__ = ["create_app"]