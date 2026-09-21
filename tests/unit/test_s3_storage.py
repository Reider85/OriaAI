"""Unit tests for S3CompatibleStorage error mapping, metadata & retry logic.

These tests mock the aiobotocore client so no MinIO instance is required.
"""
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from llm_client.storage import S3CompatibleStorage
from llm_client.storage.s3 import StorageError


def _client_error(code: str, message: str = "boom") -> ClientError:
    """Build a ClientError the way botocore raises it."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}}, operation_name="Operation"
    )


def test_map_error_404_maps_to_file_not_found():
    assert isinstance(S3CompatibleStorage._map_error(_client_error("404")), FileNotFoundError)


def test_map_error_403_maps_to_permission():
    assert isinstance(S3CompatibleStorage._map_error(_client_error("403")), PermissionError)
    assert isinstance(
        S3CompatibleStorage._map_error(_client_error("AccessDenied")), PermissionError
    )


def test_map_error_other_maps_to_storage_error():
    assert isinstance(S3CompatibleStorage._map_error(_client_error("InternalError")), StorageError)


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    storage = S3CompatibleStorage()
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _client_error("InternalError")
        return "ok"

    result = await storage._retry(flaky)
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_raises_storage_error_when_exhausted():
    storage = S3CompatibleStorage()

    async def always_fails():
        raise _client_error("InternalError")

    with pytest.raises(StorageError):
        await storage._retry(always_fails)


@pytest.mark.asyncio
async def test_retry_does_not_retry_client_errors_like_403():
    storage = S3CompatibleStorage()
    calls = {"n": 0}

    async def denied():
        calls["n"] += 1
        raise _client_error("403")

    with pytest.raises(PermissionError):
        await storage._retry(denied)
    assert calls["n"] == 1