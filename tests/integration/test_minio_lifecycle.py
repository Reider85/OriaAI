"""Integration test: S3 lifecycle (ILM) retention rules (MVP D-3 DoD, ADR-014).

BUG-MVP-02: minio-init provisions ILM rules — forensic bucket expires after 90
days, operational files bucket after 30 days. Same rules are provisioned by the
CI bucket-setup steps (phase1-ci integration-dev/staging, phase2-ci).
"""

import os

import aiobotocore.session  # type: ignore[import-untyped]
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

pytestmark = [pytest.mark.integration]

FORENSIC_BUCKET = os.getenv("S3_FORENSIC_BUCKET", "llm-client-forensic")
FILES_BUCKET = os.getenv("S3_BUCKET", "llm-client-files")
FORENSIC_RETENTION_DAYS = 90
FILES_RETENTION_DAYS = 30


async def _get_lifecycle_rules(bucket: str) -> list[dict]:
    """Return ILM rules for *bucket*.

    Skips when MinIO is down or the bucket was not provisioned. Returns an
    empty list when the bucket exists but has no lifecycle configuration —
    that case must fail the retention assertions, not skip.
    """
    session = aiobotocore.session.get_session()
    try:
        async with session.create_client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
        ) as client:
            resp = await client.get_bucket_lifecycle_configuration(Bucket=bucket)
            return resp.get("Rules", [])
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "NoSuchBucket":
            pytest.skip(
                f"bucket {bucket} not provisioned (run docker-compose up minio minio-init first)"
            )
        if code == "NoSuchLifecycleConfiguration":
            return []
        pytest.skip(f"MinIO not available: {exc}")
    except Exception as exc:  # noqa: BLE001 — probe: anything may mean MinIO is down
        pytest.skip(f"MinIO not available: {exc}")


def _expiration_days(rules: list[dict]) -> list[int]:
    return [
        rule["Expiration"]["Days"]
        for rule in rules
        if rule.get("Expiration", {}).get("Days") is not None
    ]


@pytest.mark.asyncio
async def test_forensic_bucket_has_90_day_expiry():
    rules = await _get_lifecycle_rules(FORENSIC_BUCKET)
    assert FORENSIC_RETENTION_DAYS in _expiration_days(rules), (
        f"{FORENSIC_BUCKET} must expire objects after {FORENSIC_RETENTION_DAYS} days "
        f"(MVP D-3 DoD / ADR-014); got rules={rules}"
    )


@pytest.mark.asyncio
async def test_files_bucket_has_30_day_expiry():
    rules = await _get_lifecycle_rules(FILES_BUCKET)
    assert FILES_RETENTION_DAYS in _expiration_days(rules), (
        f"{FILES_BUCKET} must expire objects after {FILES_RETENTION_DAYS} days "
        f"(ADR-014 operational retention); got rules={rules}"
    )
