"""Integration test: S3CompatibleStorage against real MinIO (Block A-2)."""
import os

import pytest

from llm_client.storage.s3 import S3CompatibleStorage

pytestmark = [pytest.mark.integration]


@pytest.fixture
async def s3_storage():
    storage = S3CompatibleStorage(
        endpoint=os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000"),
        access_key=os.getenv("S3_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
        bucket=os.getenv("S3_BUCKET", "llm-client-files"),
    )
    # Fail fast with a clear message if MinIO is not reachable.
    try:
        await storage.save(b"__probe__", "_int_probe.txt")
        await storage.delete("_int_probe.txt")
    except Exception as exc:  # noqa: BLE001 — probe anything that could mean MinIO is down
        pytest.skip(f"MinIO not available: {exc}")
    yield storage


@pytest.mark.asyncio
async def test_minio_roundtrip(s3_storage):
    key = "int/roundtrip.bin"
    data = b"binary\x00\x01\x02content" * 1000
    assert await s3_storage.save(data, key) == key
    assert await s3_storage.exists(key)
    assert await s3_storage.get(key) == data
    await s3_storage.delete(key)
    assert not await s3_storage.exists(key)


@pytest.mark.asyncio
async def test_minio_text_content(s3_storage):
    key = "int/note.txt"
    await s3_storage.save(b"hello minio", key)
    assert await s3_storage.get(key) == b"hello minio"
    await s3_storage.delete(key)


@pytest.mark.asyncio
async def test_minio_delete_missing_is_idempotent(s3_storage):
    await s3_storage.delete("int/does-not-exist.txt")


@pytest.mark.asyncio
async def test_minio_streaming(s3_storage):

    key = "int/big.bin"
    data = b"y" * 200_000
    await s3_storage.save(data, key)
    chunks = [c async for c in s3_storage.get_stream(key)]
    joined = b"".join(chunks)
    assert joined == data
    assert len(chunks) > 1  # actually exercised chunking
    await s3_storage.delete(key)


@pytest.mark.asyncio
async def test_minio_list_prefix(s3_storage):

    await s3_storage.save(b"a", "int/list/a.txt")
    await s3_storage.save(b"b", "int/list/b.txt")
    keys = await s3_storage.list("int/list/")
    assert sorted(keys) == ["int/list/a.txt", "int/list/b.txt"]
    await s3_storage.delete("int/list/a.txt")
    await s3_storage.delete("int/list/b.txt")