"""Integration test: forensic writes land in S3_FORENSIC_BUCKET, never in files bucket.

BUG-MVP-01 / ADR-014 bucket isolation. Uses the production build path
(`build_forensic_writer()`) against real MinIO, plus a files-only restricted
MinIO user for the AccessDenied regression (env-gated).

Restricted-user envs: S3_RESTRICTED_ACCESS_KEY / S3_RESTRICTED_SECRET_KEY
(provisioned by docker-compose minio-init and the integration-staging CI job).
"""

import os

import aiobotocore.session  # type: ignore[import-untyped]
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from llm_client.config import Settings
from llm_client.observability.forensic_writer import build_forensic_writer
from llm_client.observability.kms_provider import LocalDevKeyProvider
from llm_client.storage.s3 import S3CompatibleStorage

pytestmark = [pytest.mark.integration]

FILES_BUCKET = os.getenv("S3_BUCKET", "llm-client-files")


def _s3_env() -> dict[str, str]:
    return {
        "FORENSIC_STREAM_ENABLED": "true",
        "KMS_PROVIDER": "local",
        "S3_ENDPOINT": os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000"),
        "S3_ACCESS_KEY": os.getenv("S3_ACCESS_KEY", "minioadmin"),
        "S3_SECRET_KEY": os.getenv("S3_SECRET_KEY", "minioadmin"),
        "S3_BUCKET": FILES_BUCKET,
        "S3_FORENSIC_BUCKET": os.getenv("S3_FORENSIC_BUCKET", "llm-client-forensic"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "sk-test-placeholder"),
    }


@pytest.fixture
def forensic_settings():
    original_env = os.environ.copy()
    os.environ.update(_s3_env())
    try:
        settings = Settings()
        assert settings.forensic_stream_enabled is True
        yield settings
    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
async def buckets(forensic_settings):
    """Ensure both buckets exist on MinIO; yield (forensic_storage, files_storage)."""
    session = aiobotocore.session.get_session()
    try:
        async with session.create_client(
            "s3",
            endpoint_url=forensic_settings.s3_endpoint,
            aws_access_key_id=forensic_settings.s3_access_key,
            aws_secret_access_key=forensic_settings.s3_secret_key,
        ) as client:
            for bucket in (forensic_settings.s3_forensic_bucket, FILES_BUCKET):
                try:
                    await client.create_bucket(Bucket=bucket)
                except ClientError as exc:
                    code = exc.response["Error"]["Code"]
                    if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                        raise
    except Exception as exc:  # noqa: BLE001 — probe: anything may mean MinIO is down
        pytest.skip(f"MinIO not available: {exc}")

    forensic_storage = S3CompatibleStorage(
        endpoint=forensic_settings.s3_endpoint,
        access_key=forensic_settings.s3_access_key,
        secret_key=forensic_settings.s3_secret_key,
        bucket=forensic_settings.s3_forensic_bucket,
    )
    files_storage = S3CompatibleStorage(
        endpoint=forensic_settings.s3_endpoint,
        access_key=forensic_settings.s3_access_key,
        secret_key=forensic_settings.s3_secret_key,
        bucket=FILES_BUCKET,
    )
    yield forensic_storage, files_storage


async def _write_forensic_event(settings: Settings, session_id: str) -> str:
    """Write one event via the production build path; return the object key."""
    writer = build_forensic_writer(settings, LocalDevKeyProvider())
    assert writer.enabled, "forensic stream must be enabled for placement test"
    assert writer._bucket == settings.s3_forensic_bucket
    await writer.start()
    try:
        await writer.write(
            {
                "event_type": "session_cancelled",
                "session_id": session_id,
                "user_id": "placement-test",
                "reason": "user_cancelled",
                "timestamp": "2026-10-29T00:00:00Z",
                "partial_answer_size_bytes": 42,
                "last_node_executed": "final_answer",
                "messages_count": 3,
                "duration_ms": 1500,
            }
        )
        await writer.flush()
    finally:
        await writer.close()

    forensic_storage = S3CompatibleStorage(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_forensic_bucket,
    )
    keys = await forensic_storage.list("forensic/")
    matching = [k for k in keys if f"/{session_id}/" in k]
    assert matching, f"no forensic object for session {session_id} in {settings.s3_forensic_bucket}"
    return matching[0]


@pytest.mark.asyncio
async def test_forensic_object_lives_only_in_forensic_bucket(forensic_settings, buckets):
    """Object written by build_forensic_writer() exists in forensic bucket, NOT files bucket."""
    forensic_storage, files_storage = buckets
    key = await _write_forensic_event(forensic_settings, "sess-placement-1")
    try:
        assert await forensic_storage.exists(key)
        assert not await files_storage.exists(key), (
            f"forensic object leaked into {FILES_BUCKET}: {key}"
        )
        files_forensic_prefix = await files_storage.list("forensic/")
        assert key not in files_forensic_prefix
    finally:
        await forensic_storage.delete(key)


@pytest.mark.asyncio
async def test_forensic_object_denied_for_files_only_client(forensic_settings, buckets):
    """Files-only identity must get AccessDenied reading the forensic object."""
    restricted_ak = os.getenv("S3_RESTRICTED_ACCESS_KEY")
    restricted_sk = os.getenv("S3_RESTRICTED_SECRET_KEY")
    if not restricted_ak or not restricted_sk:
        pytest.skip("S3_RESTRICTED_ACCESS_KEY/SECRET not configured (files-only MinIO user)")

    forensic_storage, _files_storage = buckets
    key = await _write_forensic_event(forensic_settings, "sess-deny-1")
    try:
        restricted_forensic = S3CompatibleStorage(
            endpoint=forensic_settings.s3_endpoint,
            access_key=restricted_ak,
            secret_key=restricted_sk,
            bucket=forensic_settings.s3_forensic_bucket,
        )
        with pytest.raises(PermissionError):
            await restricted_forensic.get(key)

        restricted_files = S3CompatibleStorage(
            endpoint=forensic_settings.s3_endpoint,
            access_key=restricted_ak,
            secret_key=restricted_sk,
            bucket=FILES_BUCKET,
        )
        assert not await restricted_files.exists(key), (
            f"forensic object must not exist in {FILES_BUCKET}"
        )
    finally:
        await forensic_storage.delete(key)
