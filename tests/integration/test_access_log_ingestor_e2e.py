"""Integration test: AccessLogIngestor end-to-end (BUG-MVP-03 / MVP-PROMPTS E-4).

Full path against real MinIO: an AWS Server Access Log line lands in the
``_access_logs/`` prefix of the forensic bucket → AccessLogIngestor parses it →
ForensicStreamWriter encrypts an ``s3_access`` event into the forensic bucket →
a non-allowlisted requester triggers the security webhook alert.

Adaptation of the BUG-MVP-03 acceptance criterion («ждёт 5+ минут»): instead of
sleeping through a poll period, the test uploads a log file and drives
``ingest_once()`` directly — same code path, event-driven, CI-friendly.
"""

import json
import os
import uuid

import aiobotocore.session  # type: ignore[import-untyped]
import httpx
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from llm_client.config import Settings
from llm_client.observability.access_log_ingestor import ACCESS_LOG_PREFIX, AccessLogIngestor
from llm_client.observability.forensic_writer import build_forensic_writer
from llm_client.observability.kms_provider import EncryptedPayload, LocalDevKeyProvider
from llm_client.storage.s3 import S3CompatibleStorage

pytestmark = [pytest.mark.integration]


def _aws_log_line(bucket: str, requester: str, key: str) -> str:
    """One AWS S3 Server Access Log line (layout followed by the ingestor parser)."""
    return (
        f"79a59df900b949e55d96a1e698fbacedfd6e09d98eacf8f8d5218e7cd47ef2be {bucket} "
        f"[06/Feb/2026:00:00:38:131 +0000] 192.0.2.3 {requester} 3E57427F3EXAMPLE "
        f'REST.GET.OBJECT {key} "GET /{bucket}/{key} HTTP/1.1" '
        f'200 - 113 113 7 1 "-" "aws-sdk/2.15.0" - - - - - -'
    )


@pytest.fixture
def forensic_settings():
    original_env = os.environ.copy()
    os.environ.update(
        {
            "FORENSIC_STREAM_ENABLED": "true",
            "KMS_PROVIDER": "local",
            "S3_ENDPOINT": os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000"),
            "S3_ACCESS_KEY": os.getenv("S3_ACCESS_KEY", "minioadmin"),
            "S3_SECRET_KEY": os.getenv("S3_SECRET_KEY", "minioadmin"),
            "S3_FORENSIC_BUCKET": os.getenv("S3_FORENSIC_BUCKET", "llm-client-forensic"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "sk-test-placeholder"),
        }
    )
    try:
        settings = Settings()
        assert settings.forensic_stream_enabled is True
        yield settings
    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
async def forensic_storage(forensic_settings):
    """Forensic-bucket storage; ensures the bucket exists; skips if MinIO is down."""
    session = aiobotocore.session.get_session()
    try:
        async with session.create_client(
            "s3",
            endpoint_url=forensic_settings.s3_endpoint,
            aws_access_key_id=forensic_settings.s3_access_key,
            aws_secret_access_key=forensic_settings.s3_secret_key,
        ) as client:
            try:
                await client.create_bucket(Bucket=forensic_settings.s3_forensic_bucket)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    raise
    except Exception as exc:  # noqa: BLE001 — probe: anything may mean MinIO is down
        pytest.skip(f"MinIO not available: {exc}")

    storage = S3CompatibleStorage(
        endpoint=forensic_settings.s3_endpoint,
        access_key=forensic_settings.s3_access_key,
        secret_key=forensic_settings.s3_secret_key,
        bucket=forensic_settings.s3_forensic_bucket,
    )
    try:
        await storage.list("")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"S3 forensic bucket not available: {exc}")
    return storage


class _WebhookRecorder:
    """httpx.AsyncClient replacement capturing webhook POSTs via MockTransport."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    def install(self, monkeypatch):
        recorder = self

        def handler(request: httpx.Request) -> httpx.Response:
            recorder.requests.append(request)
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        def fake_client(*args, **kwargs):
            kwargs.setdefault("transport", transport)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", fake_client)


async def _decrypt_forensic_event(storage: S3CompatibleStorage, kms, object_key: str) -> dict:
    record = json.loads(await storage.get(object_key))
    payload = EncryptedPayload(
        ciphertext=bytes.fromhex(record["ciphertext"]),
        iv=bytes.fromhex(record["iv"]),
        key_id=record["key_id"],
        algorithm=record["algorithm"],
    )
    return json.loads(await kms.decrypt(payload))


@pytest.mark.asyncio
async def test_unauthorized_access_lands_in_forensic_and_alerts(
    forensic_settings, forensic_storage, monkeypatch
):
    """Non-allowlisted requester → encrypted s3_access event + Slack webhook alert."""
    run_id = uuid.uuid4().hex[:8]
    evil_requester = f"evil-actor-{run_id}"
    log_key = f"{ACCESS_LOG_PREFIX}e2e-{run_id}.log"
    kms = LocalDevKeyProvider()
    writer = build_forensic_writer(forensic_settings, kms)

    before_keys = set(await forensic_storage.list("forensic/"))
    await forensic_storage.save(
        (
            _aws_log_line(
                forensic_settings.s3_forensic_bucket,
                evil_requester,
                f"forensic/2026/02/06/{run_id}.json",
            )
            + "\n"
        ).encode(),
        log_key,
    )

    webhook = _WebhookRecorder()
    webhook.install(monkeypatch)
    ingestor = AccessLogIngestor(
        forensic_writer=writer,
        s3_client=forensic_storage,
        bucket=forensic_settings.s3_forensic_bucket,
        allowlist=["llm-client-service"],
        security_webhook_url="https://hooks.slack.com/services/e2e-test",
    )

    try:
        await writer.start()
        await ingestor.ingest_once()
        await writer.flush()

        # 1) Encrypted s3_access event landed in the forensic bucket
        new_keys = set(await forensic_storage.list("forensic/")) - before_keys
        assert new_keys, "no forensic object written for the ingested access log"
        events = [await _decrypt_forensic_event(forensic_storage, kms, k) for k in new_keys]
        s3_events = [e for e in events if e.get("event_type") == "s3_access"]
        assert s3_events, f"no s3_access event among forensic objects: {events!r}"
        event = s3_events[0]
        assert event["requester"] == evil_requester
        assert event["bucket"] == forensic_settings.s3_forensic_bucket
        assert event["operation"] == "REST.GET.OBJECT"
        assert event["status"] == 200
        assert event["bytes_transferred"] == 113

        # 2) Security webhook alert fired for the non-allowlisted requester
        assert webhook.requests, "no webhook alert sent for non-allowlisted requester"
        bodies = [r.content.decode("utf-8", errors="replace") for r in webhook.requests]
        assert any("non-allowlisted requester" in b and evil_requester in b for b in bodies), (
            f"webhook payloads do not mention the violator: {bodies!r}"
        )
    finally:
        for k in set(await forensic_storage.list("forensic/")) - before_keys:
            await forensic_storage.delete(k)
        await forensic_storage.delete(log_key)
        await writer.close()


@pytest.mark.asyncio
async def test_allowlisted_requester_ingested_without_alert(
    forensic_settings, forensic_storage, monkeypatch
):
    """Allowlisted requester still lands in forensic, but no alert is sent."""
    run_id = uuid.uuid4().hex[:8]
    log_key = f"{ACCESS_LOG_PREFIX}e2e-allow-{run_id}.log"
    kms = LocalDevKeyProvider()
    writer = build_forensic_writer(forensic_settings, kms)

    before_keys = set(await forensic_storage.list("forensic/"))
    await forensic_storage.save(
        (
            _aws_log_line(
                forensic_settings.s3_forensic_bucket,
                "llm-client-service",
                f"forensic/2026/02/06/{run_id}.json",
            )
            + "\n"
        ).encode(),
        log_key,
    )

    webhook = _WebhookRecorder()
    webhook.install(monkeypatch)
    ingestor = AccessLogIngestor(
        forensic_writer=writer,
        s3_client=forensic_storage,
        bucket=forensic_settings.s3_forensic_bucket,
        allowlist=["llm-client-service"],
        security_webhook_url="https://hooks.slack.com/services/e2e-test",
    )

    try:
        await writer.start()
        await ingestor.ingest_once()
        await writer.flush()

        new_keys = set(await forensic_storage.list("forensic/")) - before_keys
        assert new_keys, "allowlisted access must still be audited in forensic"
        assert webhook.requests == [], (
            f"alert must not fire for allowlisted requester: {webhook.requests!r}"
        )
    finally:
        for k in set(await forensic_storage.list("forensic/")) - before_keys:
            await forensic_storage.delete(k)
        await forensic_storage.delete(log_key)
        await writer.close()


@pytest.mark.asyncio
async def test_ingestor_start_close_lifecycle(caplog):
    """start() spawns the poll loop and logs it; close() cancels the task."""

    class _EmptyS3:
        async def list(self, prefix: str = "") -> list[str]:
            return []

        async def get(self, key: str) -> bytes:
            raise FileNotFoundError(key)

    ingestor = AccessLogIngestor(
        forensic_writer=object(),  # type: ignore[arg-type] — never used in this test
        s3_client=_EmptyS3(),
        poll_interval_seconds=300,
        allowlist=["llm-client-service"],
    )
    with caplog.at_level("INFO", logger="llm_client.observability.access_log_ingestor"):
        await ingestor.start()
        assert ingestor._task is not None and not ingestor._task.done()
        assert "AccessLogIngestor started" in caplog.text
        await ingestor.close()
        assert ingestor._task.done()
