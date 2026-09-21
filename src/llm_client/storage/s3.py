"""S3-compatible storage adapter (extended ADR-008, Block E).

Uses aiobotocore for async operations. MinIO in dev, AWS S3 in prod.
Supports: multipart upload (>5 MB), metadata, retry with exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import BinaryIO

import aiobotocore.session  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from .base import FileStorage

logger = logging.getLogger(__name__)

MULTIPART_THRESHOLD = 5 * 1024 * 1024  # 5 MB
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.001  # 1 ms


class S3Error(Exception):
    """Base S3 storage error."""


class StorageError(S3Error):
    """Generic storage error after retries exhausted."""


class S3CompatibleStorage(FileStorage):
    """S3-compatible storage via aiobotocore. MinIO in dev, AWS S3 in prod.

    Config from env: S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET.
    Extended ADR-008 (Block E) — production-quality implementation.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
    ) -> None:
        self._endpoint = endpoint or os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000")
        self._access_key = access_key or os.getenv("S3_ACCESS_KEY", "minioadmin")
        self._secret_key = secret_key or os.getenv("S3_SECRET_KEY", "minioadmin")
        self._bucket = bucket or os.getenv("S3_BUCKET", "llm-client-files")
        self._session = aiobotocore.session.get_session()

    def _client(self):  # type: ignore[no-untyped-def]
        return self._session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )

    @staticmethod
    def _map_error(exc: ClientError) -> Exception:
        code = exc.response["Error"]["Code"]
        if code == "404":
            return FileNotFoundError(str(exc))
        if code in ("403", "AccessDenied"):
            return PermissionError(str(exc))
        return StorageError(str(exc))

    async def _retry(self, factory: object) -> object:
        """Execute the coroutine returned by *factory* with exp-backoff retry.

        *factory* is a callable producing a fresh coroutine per attempt — a single
        coroutine object cannot be awaited twice after a transient failure.
        """
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                coro = factory()  # type: ignore[operator]
                return await coro
            except ClientError as exc:
                mapped = self._map_error(exc)
                if isinstance(mapped, (FileNotFoundError, PermissionError)):
                    raise mapped from exc
                last_exc = exc
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
            delay = RETRY_BASE_DELAY * (2**attempt)
            logger.debug("S3 retry %d/%d after %.3fs", attempt + 1, MAX_RETRIES, delay)
            await asyncio.sleep(delay)
        raise StorageError(
            f"S3 operation failed after {MAX_RETRIES} retries: {last_exc}"
        )

    # ── FileStorage interface ───────────────────────────────────────────────

    async def save(  # type: ignore[override]
        self, file: bytes | BinaryIO, key: str, metadata: dict[str, str] | None = None
    ) -> str:
        data = file.read() if hasattr(file, "read") else file  # type: ignore[union-attr]

        async def _put() -> None:
            async with self._client() as client:
                await client.put_object(
                    Bucket=self._bucket, Key=key, Body=data, Metadata=metadata or {}
                )

        if len(data) > MULTIPART_THRESHOLD:
            await self._save_multipart(data, key, metadata)
        else:
            await self._retry(_put)
        return key

    async def _save_multipart(
        self, data: bytes, key: str, metadata: dict[str, str] | None
    ) -> None:
        async with self._client() as client:
            mpu = await client.create_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                Metadata=metadata or {},
            )
            parts: list[dict] = []
            chunk_size = 8 * 1024 * 1024  # 8 MB per part
            try:
                for i in range(0, len(data), chunk_size):
                    chunk = data[i : i + chunk_size]
                    part = await client.upload_part(
                        Bucket=self._bucket,
                        Key=key,
                        UploadId=mpu["UploadId"],
                        PartNumber=len(parts) + 1,
                        Body=chunk,
                    )
                    parts.append(
                        {"PartNumber": len(parts) + 1, "ETag": part["ETag"]}
                    )
                await client.complete_multipart_upload(
                    Bucket=self._bucket,
                    Key=key,
                    UploadId=mpu["UploadId"],
                    MultipartUpload={"Parts": parts},
                )
            except Exception:
                await client.abort_multipart_upload(
                    Bucket=self._bucket, Key=key, UploadId=mpu["UploadId"]
                )
                raise

    async def get(self, key: str) -> bytes:
        async with self._client() as client:
            try:
                resp = await client.get_object(Bucket=self._bucket, Key=key)
                async with resp["Body"] as stream:
                    return await stream.read()
            except ClientError as exc:
                mapped = self._map_error(exc)
                if isinstance(mapped, FileNotFoundError):
                    raise FileNotFoundError(key) from exc
                raise mapped from exc

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        async with self._client() as client:
            try:
                resp = await client.get_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                mapped = self._map_error(exc)
                if isinstance(mapped, FileNotFoundError):
                    raise FileNotFoundError(key) from exc
                raise mapped from exc
            async with resp["Body"] as stream:
                while chunk := await stream.read(65536):
                    yield chunk

    async def delete(self, key: str) -> None:
        async def _delete() -> None:
            async with self._client() as client:
                await client.delete_object(Bucket=self._bucket, Key=key)

        await self._retry(_delete)

    async def exists(self, key: str) -> bool:
        async def _head() -> None:
            async with self._client() as client:
                await client.head_object(Bucket=self._bucket, Key=key)

        try:
            await self._retry(_head)
            return True
        except FileNotFoundError:
            return False

    async def list(self, prefix: str = "") -> list[str]:
        async with self._client() as client:
            keys: list[str] = []
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
            return keys