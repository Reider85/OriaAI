"""ForensicStreamWriter — encrypted full-trace logging to a dedicated S3 bucket (ADR-014, D-3).

Writes unfiltered events, encrypts them with KMS (AES-256-GCM via Vault transit,
Block A-3 / D-4), and uploads to the ``S3_FORENSIC_BUCKET`` under
``forensic/YYYY/MM/DD/{session_id}/...``. Writes are batched (flush every
``flush_interval_ms`` or ``max_batch_size`` events).

Behaviour:
  * disabled mode (dev): ``write()`` is a no-op and a startup warning is logged.
  * encryption/S3 failures are NEVER swallowed — a ForensicWriteError is raised so
    the caller can fail the request (privacy-first: no plaintext fallback).
"""
import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from ..storage.base import FileStorage
from .kms_provider import KMSKeyProvider

logger = logging.getLogger(__name__)


class ForensicWriteError(RuntimeError):
    """Raised when a forensic record cannot be written (encryption or S3 failure)."""


class ForensicStreamWriter:
    """Encrypts forensic events via KMS and stores them in the forensic S3 bucket."""

    def __init__(
        self,
        kms_provider: KMSKeyProvider,
        s3_client: FileStorage,
        bucket: str = "llm-client-forensic",
        enabled: bool = True,
        *,
        flush_interval_ms: float = 500.0,
        max_batch_size: int = 50,
    ) -> None:
        self._kms = kms_provider
        self._s3 = s3_client
        self._bucket = bucket
        self._enabled = enabled
        self._flush_interval = flush_interval_ms / 1000.0
        self._max_batch = max_batch_size
        self._buffer: list[tuple[dict[str, str], str]] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._closed = False

        if not enabled:
            logger.warning("Forensic stream disabled — forensic writes are no-ops")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        if self._enabled:
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def write(self, event: dict) -> None:
        """Encrypt ``event`` and schedule it for the forensic bucket. No PII masking."""
        if not self._enabled:
            return

        serialized = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            payload = await self._kms.encrypt(serialized)
        except Exception as exc:
            logger.error("Forensic encryption failed for event %s: %s", event.get("event_type"), exc)
            raise ForensicWriteError("forensic encryption failed") from exc

        session_id = event.get("session_id", "unknown")
        object_key = self._object_key(session_id)
        record = {
            "ciphertext": payload.ciphertext.hex(),
            "iv": payload.iv.hex(),
            "key_id": payload.key_id,
            "algorithm": payload.algorithm,
            "key_path": object_key,
        }
        async with self._lock:
            self._buffer.append((record, object_key))
            flush_now = len(self._buffer) >= self._max_batch
        if flush_now:
            await self._flush()

    async def flush(self) -> None:
        if self._enabled and not self._closed:
            await self._flush()

    async def close(self) -> None:
        self._closed = True
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()

    async def _flush_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            pending = self._buffer
            self._buffer = []
        for record, key in pending:
            body = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            try:
                await self._s3.save(body, key)
            except Exception as exc:
                raise ForensicWriteError(f"forensic S3 write failed for {key}") from exc

    @staticmethod
    def _object_key(session_id: str) -> str:
        now = datetime.now(UTC)
        return (
            f"forensic/{now.year}/{now.month:02d}/{now.day:02d}/"
            f"{session_id}/{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}.json"
        )


def build_forensic_writer(
    settings: Any,
    kms_provider: KMSKeyProvider,
    s3_client: FileStorage,
) -> ForensicStreamWriter:
    """Build writer wired to app settings (S3_FORENSIC_BUCKET, FORENSIC_STREAM_ENABLED)."""
    return ForensicStreamWriter(
        kms_provider=kms_provider,
        s3_client=s3_client,
        bucket=getattr(settings, "s3_forensic_bucket", "llm-client-forensic"),
        enabled=bool(getattr(settings, "forensic_stream_enabled", False)),
    )


__all__ = ["ForensicStreamWriter", "ForensicWriteError", "build_forensic_writer"]