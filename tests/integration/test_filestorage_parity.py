"""F-3: MinIO parity test (extended ADR-008) — one FileStorage contract across
dev (MinIO), staging (external MinIO), prod (S3).

Run a target explicitly with FILESTORAGE_BACKEND=minio_dev|minio_staging|s3_prod.
Defaults to minio_dev when unset (local dev). The CI matrix runs one target per
job (F-4): dev on every PR, staging+prod nightly.

Each operating on a target whose config is not reachable is skipped with a clear
message; if staging/prod env vars are absent, only dev runs locally.
"""

import asyncio
import importlib
import os

import pytest

from llm_client.storage.s3 import S3CompatibleStorage

pytestmark = [pytest.mark.integration]

TARGETS = ("minio_dev", "minio_staging", "s3_prod")
# Extended ADR-008 parity: large-file round-trip (multipart > 5 MB is exercised).
LARGE_FILE_BYTES = int(os.getenv("PARITY_LARGE_FILE_BYTES", str(50 * 1024 * 1024)))
CONCURRENT_SAVES = 10


def _active_targets() -> list[str]:
    """The target(s) to run. FILESTORAGE_BACKEND selects one (CI matrix); the
    default is local dev MinIO so `pytest -m integration` works out of the box."""
    target = os.getenv("FILESTORAGE_BACKEND")
    if target is not None:
        assert target in TARGETS, f"FILESTORAGE_BACKEND must be one of {TARGETS}, got {target!r}"
        return [target]
    return ["minio_dev"]


def _config_for(target: str) -> dict:
    if target == "minio_dev":
        return {
            "endpoint": os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000"),
            "access_key": os.getenv("S3_ACCESS_KEY", "minioadmin"),
            "secret_key": os.getenv("S3_SECRET_KEY", "minioadmin"),
            "bucket": os.getenv("S3_BUCKET", "llm-client-files"),
            "skip_when_unset": False,
        }
    suffix = "_STAGING" if target == "minio_staging" else "_PROD"
    return {
        "endpoint": os.getenv(f"S3{suffix}_ENDPOINT"),
        "access_key": os.getenv(f"S3{suffix}_ACCESS_KEY"),
        "secret_key": os.getenv(f"S3{suffix}_SECRET_KEY"),
        "bucket": os.getenv(f"S3{suffix}_BUCKET", "llm-client-files"),
        "skip_when_unset": True,
    }


@pytest.fixture
async def storage(target):
    cfg = _config_for(target)
    if cfg["skip_when_unset"] and not cfg["endpoint"]:
        pytest.skip(
            f"parity target {target} not configured — set S3{'_STAGING' if target == 'minio_staging' else '_PROD'}_ENDPOINT"
        )
    storage = S3CompatibleStorage(
        endpoint=cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        bucket=cfg["bucket"],
    )
    # Fail fast with a clear message if the target backend is not reachable.
    try:
        await storage.save(b"__parity_probe__", "_parity/probe.txt")
        await storage.delete("_parity/probe.txt")
    except Exception as exc:  # noqa: BLE001 — probe anything that could mean the backend is down
        pytest.skip(f"parity target {target} not available: {exc}")
    yield storage


def _large_payload(size: int) -> bytes:
    chunk = b"0123456789abcdef" * (64 * 1024)  # 1 MiB unit
    return (chunk * (size // len(chunk))) + chunk[: size % len(chunk)]


@pytest.mark.parametrize("target", _active_targets(), ids=_active_targets())
@pytest.mark.asyncio
async def test_parity_save_get_exists_delete(storage, target):
    key = f"_parity/{target}/roundtrip.bin"
    data = b"parity\x00\xffpayload" * 4096
    assert await storage.save(data, key) == key
    assert await storage.exists(key)
    assert await storage.get(key) == data
    await storage.delete(key)
    assert not await storage.exists(key)


@pytest.mark.parametrize("target", _active_targets(), ids=_active_targets())
@pytest.mark.asyncio
async def test_parity_large_file_roundtrip(storage, target):
    key = f"_parity/{target}/large.bin"
    data = _large_payload(LARGE_FILE_BYTES)
    try:
        assert await storage.save(data, key) == key
        assert await storage.exists(key)
        assert await storage.get(key) == data
    finally:
        await storage.delete(key)


@pytest.mark.parametrize("target", _active_targets(), ids=_active_targets())
@pytest.mark.asyncio
async def test_parity_save_with_metadata(storage, target):
    key = f"_parity/{target}/meta.txt"
    data = b"metadata payload"
    try:
        await storage.save(
            data, key, metadata={"content_type": "text/plain", "owner": "parity-test"}
        )
        assert await storage.get(key) == data
        assert await storage.exists(key)
    finally:
        await storage.delete(key)


@pytest.mark.parametrize("target", _active_targets(), ids=_active_targets())
@pytest.mark.asyncio
async def test_parity_list_prefix(storage, target):
    prefix = f"_parity/{target}/list/"
    keys = [f"{prefix}a.txt", f"{prefix}b.txt", f"{prefix}sub/c.txt"]
    try:
        for key in keys:
            await storage.save(b"x", key)
        found = await storage.list(prefix)
        assert sorted(found) == sorted(keys)
    finally:
        for key in keys:
            await storage.delete(key)


@pytest.mark.parametrize("target", _active_targets(), ids=_active_targets())
@pytest.mark.asyncio
async def test_parity_get_stream(storage, target):
    key = f"_parity/{target}/stream.bin"
    data = _large_payload(2 * 1024 * 1024)
    try:
        await storage.save(data, key)
        chunks = [chunk async for chunk in storage.get_stream(key)]
        joined = b"".join(chunks)
        assert joined == data
        assert len(chunks) >= 1
    finally:
        await storage.delete(key)


@pytest.mark.parametrize("target", _active_targets(), ids=_active_targets())
@pytest.mark.asyncio
async def test_parity_concurrent_saves(storage, target):
    prefix = f"_parity/{target}/concurrent/"

    async def save_one(i: int) -> None:
        await storage.save(b"c" * i, f"{prefix}{i}.bin")

    try:
        await asyncio.gather(*(save_one(i) for i in range(CONCURRENT_SAVES)))
        found = await storage.list(prefix)
        assert len(found) == CONCURRENT_SAVES
        for i in range(CONCURRENT_SAVES):
            assert await storage.get(f"{prefix}{i}.bin") == b"c" * i
    finally:
        for i in range(CONCURRENT_SAVES):
            await storage.delete(f"{prefix}{i}.bin")


@pytest.mark.parametrize("target", _active_targets(), ids=_active_targets())
@pytest.mark.asyncio
async def test_parity_delete_missing_is_idempotent(storage, target):
    await storage.delete(f"_parity/{target}/does-not-exist.txt")


# ---------------------------------------------------------------------------
# F-3 DoD: LocalFileStorage is gone (extended ADR-008 / Block E-2)
# ---------------------------------------------------------------------------


def test_local_filestorage_removed():
    """`from llm_client.storage import LocalFileStorage` must FAIL with ImportError."""
    with pytest.raises(ImportError):
        importlib.import_module("llm_client.storage.local")
