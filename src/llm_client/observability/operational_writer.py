"""OperationalStreamWriter — masked operational logs to stdout/Loki/ELK (ADR-014, D-2).

Writes JSON events that have had every PII occurrence masked via PIIDetector.
Supports a pluggable ``LogSink`` (stdout default, Loki / ELK for staging/prod).
Writes are async and buffered: a batch flush fires every ``flush_interval_ms`` or
``max_batch_size`` events, whichever comes first.
"""
import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from ..security.pii_detector import PIIDetector

logger = logging.getLogger(__name__)


class LogSink(ABC):
    """Output target for masked operational events."""

    @abstractmethod
    async def write_batch(self, events: list[str]) -> None:
        """Persist a batch of serialized (masked) JSON event strings."""


class StdoutSink(LogSink):
    """Prints each event as a JSON line to stdout (default for dev via docker logs)."""

    async def write_batch(self, events: list[str]) -> None:
        for event in events:
            print(event, flush=True)


class LokiSink(LogSink):
    """HTTP POST each batch to a Loki push endpoint (staging/prod)."""

    def __init__(self, url: str, **kwargs: Any) -> None:
        import httpx

        self._url = url.rstrip("/") + "/loki/api/v1/push"
        self._client = httpx.AsyncClient(timeout=5.0)

    async def write_batch(self, events: list[str]) -> None:
        if not events:
            return
        stream = [
            {"stream": {"app": "llm-client", "source": "operational"}, "values": [[str(int(time.time() * 1e9)), ev]]}
            for ev in events
        ]
        resp = await self._client.post(self._url, json={"streams": stream})
        resp.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()


class ELKSink(LogSink):
    """HTTP POST each event to Elasticsearch _bulk endpoint."""

    def __init__(self, url: str, **kwargs: Any) -> None:
        import httpx

        self._url = url.rstrip("/") + "/_bulk"
        self._client = httpx.AsyncClient(timeout=5.0)

    async def write_batch(self, events: list[str]) -> None:
        if not events:
            return
        payload = "".join(
            f'{{"index":{{"index":"llm-client-operational"}}}}\n{ev}\n' for ev in events
        )
        resp = await self._client.post(self._url, content=payload, headers={"Content-Type": "application/x-ndjson"})
        resp.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()


class OperationalStreamWriter:
    """Masks PII in events then asynchronously writes them to the configured sink."""

    def __init__(
        self,
        pii_detector: PIIDetector,
        sink: LogSink | None = None,
        *,
        flush_interval_ms: float = 100.0,
        max_batch_size: int = 100,
    ) -> None:
        self._pii = pii_detector
        self._sink: LogSink = sink or StdoutSink()
        self._flush_interval = flush_interval_ms / 1000.0
        self._max_batch = max_batch_size
        self._buffer: list[str] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def write(self, event: dict) -> None:
        """Serialize ``event``, mask PII recursively, enqueue to the batch buffer."""
        masked = _mask_event(event, self._pii)
        line = json.dumps(masked, ensure_ascii=False, separators=(",", ":"))
        async with self._lock:
            self._buffer.append(line)
            flush_now = len(self._buffer) >= self._max_batch

        if not self._closed and flush_now:
            await self._flush()

    async def flush(self) -> None:
        """Force flush of the current buffer regardless of size."""
        if not self._closed:
            await self._flush()

    async def close(self) -> None:
        self._closed = True
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()
        if isinstance(self._sink, StdoutSink):
            return
        close = getattr(self._sink, "close", None)
        if close is not None:
            await close()

    async def _flush_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            batch = self._buffer
            self._buffer = []
        if not batch:
            return
        try:
            await self._sink.write_batch(batch)
        except Exception:
            logger.exception("OperationalStreamWriter failed to flush %d events", len(batch))
            # Re-enqueue so nothing is silently lost (best-effort).
            async with self._lock:
                self._buffer = batch + self._buffer


def _mask_event(event: dict, pii: PIIDetector) -> dict:
    """Recursively mask string values in ``event`` (nested dicts/lists included)."""

    def _mask_value(value: Any) -> Any:
        if isinstance(value, str):
            return pii.mask(value)
        if isinstance(value, dict):
            return {k: _mask_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_mask_value(v) for v in value]
        return value

    return {k: _mask_value(v) for k, v in event.items()}


def build_operational_writer(settings: Any, pii_detector: PIIDetector | None = None) -> OperationalStreamWriter:
    """Build writer from app settings (OPERATIONAL_LOG_SINK=stdout|loki|elk)."""
    from ..security.pii_detector import PIIDetector

    sink_name = getattr(settings, "operational_log_sink", "stdout").lower()
    sink: LogSink
    if sink_name == "loki":
        sink = LokiSink(settings.operational_log_loki_url)
    elif sink_name == "elk":
        sink = ELKSink(settings.operational_log_es_url)
    else:
        sink = StdoutSink()

    if pii_detector is None:
        pii_detector = PIIDetector(
            spacy_model=getattr(settings, "pii_detector_spacy_model", "en_core_web_md"),
            enabled=bool(getattr(settings, "pii_detector_enabled", True)),
        )
    return OperationalStreamWriter(pii_detector, sink=sink)


__all__ = [
    "ELKSink",
    "LogSink",
    "LokiSink",
    "OperationalStreamWriter",
    "StdoutSink",
    "build_operational_writer",
]