"""Unit tests for AccessLogIngestor (Block E-4)."""
import pytest

from llm_client.observability.access_log_ingestor import AccessLogIngestor

SAMPLE_LINE = (
    "79a59df900b949e55d96a1e698fbacedfd6e09d98eacf8f8d5218e7cd47ef2be llm-client-forensic "
    "[06/Feb/2026:00:00:38:131 +0000] 192.0.2.3 llm-client-service 3E57427F3EXAMPLE "
    'REST.GET.OBJECT forensic/2026/02/06/x.json "GET /llm-client-forensic/forensic/2026/02/06/x.json HTTP/1.1" '
    "200 - 113 113 7 1 \"-\" \"aws-sdk/2.15.0\" - - - - - -"
)


class RecordingWriter:
    """Captures events passed to write() so tests can inspect them."""

    def __init__(self):
        self.events: list[dict] = []

    async def write(self, event: dict) -> None:
        self.events.append(event)


class FakeS3:
    """Minimal FileStorage double backed by a dict of key -> bytes."""

    def __init__(self, objects: dict[str, bytes]):
        self._objects = objects

    async def list(self, prefix: str = "") -> list[str]:
        return [k for k in self._objects if k.startswith(prefix)]

    async def get(self, key: str) -> bytes:
        if key not in self._objects:
            raise FileNotFoundError(key)
        value = self._objects[key]
        return value.encode() if isinstance(value, str) else value

    async def save(self, file, key):
        return key


@pytest.mark.asyncio
async def test_ingest_parses_s3_access_line():
    log_key = "_access_logs/2026-02-06-00-00-38.log"
    ingestor = AccessLogIngestor(
        forensic_writer=RecordingWriter(),
        s3_client=FakeS3({log_key: (SAMPLE_LINE + "\n").encode()}),
        allowlist=["llm-client-service"],
    )
    assert ingestor is not None
    ingestor._last_marker = None
    ingestor._bucket = "llm-client-forensic"
    await ingestor.ingest_once()

    assert len(ingestor._writer.events) == 1  # type: ignore[attr-defined]
    event = ingestor._writer.events[0]  # type: ignore[attr-defined]
    assert event["event_type"] == "s3_access"
    assert event["bucket"] == "llm-client-forensic"
    assert event["key"] == "forensic/2026/02/06/x.json"
    assert event["operation"] == "REST.GET.OBJECT"
    assert event["requester"] == "llm-client-service"
    assert event["request_id"] == "3E57427F3EXAMPLE"
    assert event["bytes_transferred"] == 113
    assert event["status"] == 200
    assert ingestor._last_marker == log_key


@pytest.mark.asyncio
async def test_ingest_skips_unparseable_lines():
    ingestor = AccessLogIngestor(
        forensic_writer=RecordingWriter(),
        s3_client=FakeS3({"_access_logs/bad.log": "garbage line\n"}),
    )
    ingestor._bucket = "llm-client-forensic"
    await ingestor.ingest_once()
    assert ingestor._writer.events == []  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_non_allowed_requester_warns_without_webhook(caplog):
    ingestor = AccessLogIngestor(
        forensic_writer=RecordingWriter(),
        s3_client=FakeS3({"_access_logs/blocked.log": SAMPLE_LINE + "\n"}),
        allowlist=["svc-other"],
        security_webhook_url="https://hooks.slack.com/services/placeholder",
    )
    ingestor._bucket = "llm-client-forensic"
    with caplog.at_level("WARNING", logger="llm_client.observability.access_log_ingestor"):
        await ingestor.ingest_once()
    # Even though requester is blocked, the event still lands in forensic.
    assert len(ingestor._writer.events) == 1  # type: ignore[attr-defined]
    assert "non-allowlisted requester" in caplog.text


@pytest.mark.asyncio
async def test_only_new_entries_after_marker():
    ingestor = AccessLogIngestor(
        forensic_writer=RecordingWriter(),
        s3_client=FakeS3(
            {
                "_access_logs/a.log": SAMPLE_LINE + "\n",
                "_access_logs/b.log": SAMPLE_LINE + "\n",
            }
        ),
    )
    ingestor._bucket = "llm-client-forensic"
    ingestor._last_marker = "_access_logs/a.log"
    await ingestor.ingest_once()
    assert len(ingestor._writer.events) == 1  # type: ignore[attr-defined]