"""AccessLogIngestor — S3/MinIO access logs into the forensic stream (Block E-4).

Scans the forensic bucket's ``_access_logs/`` prefix every few minutes, parses
each Server Access Log entry into a structured ``s3_access`` event and pushes it
through ForensicStreamWriter (encrypted full trace). If the requester is not in
the allow-list, a security alert is fired to the configured webhook.

The segment of parsing follows the AWS S3 Server Access Log field layout:
    bucket-owner bucket [time] remote-ip requester request-id operation key
    request-uri http-status error-code bytes-sent object-size total-time
    turn-around-time referrer user-agent version-id host-id ...
"""
import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

from .forensic_writer import ForensicStreamWriter

logger = logging.getLogger(__name__)

ACCESS_LOG_PREFIX = "_access_logs/"
DEFAULT_POLL_INTERVAL_SECONDS = 300  # 5 minutes
MAX_ENTRIES_PER_POLL = 1000
SECURITY_WEBHOOK_URL = "https://hooks.slack.com/services/placeholder"  # overridden via env

# Standard S3 Server Access Log lines have bracketed timestamps and quoted request URI.
_LINE_RE = re.compile(
    r"^\S+\s+(?P<bucket>\S+)\s+\[(?P<time>[^\]]+)\]\s+"
    r"(?P<remote_ip>\S+)\s+(?P<requester>\S+)\s+(?P<request_id>\S+)\s+"
    r"(?P<operation>\S+)\s+(?P<key>\S+)\s+"
    r"(?P<request_uri>\"[^\"]*\")\s+(?P<status>\S+)\s+(?P<error_code>\S*)\s+"
    r"(?P<bytes_sent>\S+)\s+(?P<object_size>\S+)\s+"
    r"(?P<total_time>\S+)\s+(?P<turn_around>\S+)\s+"
    r"(?P<referrer>\"[^\"]*\")\s+(?P<user_agent>\"[^\"]*\")"
)


class AccessLogIngestor:
    """Background task: ingests S3 access logs into the forensic stream."""

    def __init__(
        self,
        forensic_writer: ForensicStreamWriter,
        s3_client: Any,
        bucket: str | None = None,
        *,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
        allowlist: list[str] | None = None,
        security_webhook_url: str | None = None,
    ) -> None:
        self._writer = forensic_writer
        self._s3 = s3_client
        self._bucket = bucket or "/"
        self._poll_interval = poll_interval_seconds
        self._allowlist: set[str] = set(allowlist or self._default_allowlist())
        self._webhook_url = security_webhook_url or self._default_webhook()
        self._task: asyncio.Task | None = None
        self._last_marker: str | None = None
        self._closed = False

    @staticmethod
    def _default_allowlist() -> list[str]:
        import os

        return [
            v.strip()
            for v in os.getenv("S3_ACCESS_LOG_ALLOWLIST", "llm-client-service").split(",")
            if v.strip()
        ]

    @staticmethod
    def _default_webhook() -> str:
        import os

        return os.getenv("SECURITY_ALERT_WEBHOOK_URL", SECURITY_WEBHOOK_URL)

    async def start(self) -> None:
        if self._closed:
            return
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("AccessLogIngestor started (poll every %ds, allowlist=%s)", self._poll_interval, sorted(self._allowlist))

    async def close(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        while not self._closed:
            try:
                await self.ingest_once()
            except Exception:
                logger.exception("AccessLogIngestor poll failed")
            await asyncio.sleep(self._poll_interval)

    async def ingest_once(self) -> None:
        """Read new access log objects and forward parsed events to the forensic stream."""
        keys = await self._s3.list(ACCESS_LOG_PREFIX)
        keys.sort()
        if self._last_marker is not None:
            keys = [k for k in keys if k > self._last_marker]
        keys = keys[:MAX_ENTRIES_PER_POLL]

        for key in keys:
            try:
                raw = (await self._s3.get(key)).decode("utf-8", errors="replace")
            except FileNotFoundError:
                continue
            for line in raw.splitlines():
                if not line.strip():
                    continue
                event = self._parse_line(line, key)
                if event is None:
                    continue
                await self._writer.write(event)
                if not self._is_allowed(event["requester"]):
                    await self._alert(event)
            self._last_marker = key

    def _parse_line(self, line: str, source_key: str) -> dict | None:
        """Parse a single Server Access Log line into an ``s3_access`` event."""
        match = _LINE_RE.match(line)
        now = datetime.now(UTC).isoformat(timespec="milliseconds")
        if match is None:
            logger.debug("[access_log] unparseable line from %s: %s", source_key, line[:120])
            return None

        g = match.groupdict()
        operation = g["operation"]
        key = g["key"]
        status = g["status"]

        event: dict[str, Any] = {
            "event_type": "s3_access",
            "bucket": g["bucket"],
            "key": key,
            "operation": operation,
            "requester": g["requester"],
            "timestamp": g["time"],
            "request_id": g["request_id"],
            "bytes_transferred": self._to_int(g["bytes_sent"]),
            "object_size": self._to_int(g["object_size"]),
            "status": self._to_int(status) if status.isdigit() else status,
            "error_code": g["error_code"] or None,
            "source_key": source_key,
            "ingested_at": now,
        }
        return event

    def _is_allowed(self, requester: str) -> bool:
        return requester in self._allowlist

    async def _alert(self, event: dict) -> None:
        if self._webhook_url == SECURITY_WEBHOOK_URL:
            logger.warning(
                "[security] S3 access by non-allowlisted requester %s: %s %s (webhook not configured)",
                event["requester"],
                event["operation"],
                event["key"],
            )
            return
        try:
            import httpx

            payload = {
                "text": (
                    f"S3 access by non-allowlisted requester `{event['requester']}`: "
                    f"{event['operation']} {event['key']} (bucket {event['bucket']})."
                )
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self._webhook_url, json=payload)
            logger.info("[security] alert sent for non-allowlisted access by %s", event["requester"])
        except Exception:
            logger.exception("[security] alert delivery failed for %s", event["requester"])

    @staticmethod
    def _to_int(value: str) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


__all__ = ["ACCESS_LOG_PREFIX", "AccessLogIngestor"]