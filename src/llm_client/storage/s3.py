from collections.abc import AsyncIterator
from typing import BinaryIO

import aiobotocore.session  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from .base import FileStorage


class S3CompatibleStorage(FileStorage):
    """S3-compatible storage via aiobotocore. MinIO in dev, AWS S3 in prod.

    Config from env: S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET.
    Quick Win B-2 + later full extended ADR-008 (Block E) implementation.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
    ) -> None:
        import os

        self._endpoint = endpoint or os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000")
        self._access_key = access_key or os.getenv("S3_ACCESS_KEY", "minioadmin")
        self._secret_key = secret_key or os.getenv("S3_SECRET_KEY", "minioadmin")
        self._bucket = bucket or os.getenv("S3_BUCKET", "llm-client-files")
        self._session = aiobotocore.session.get_session()

    def _client(self):
        return self._session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )

    async def save(self, file: bytes | BinaryIO, key: str) -> str:
        async with self._client() as client:
            await client.put_object(Bucket=self._bucket, Key=key, Body=file)
        return key

    async def get(self, key: str) -> bytes:
        async with self._client() as client:
            resp = await client.get_object(Bucket=self._bucket, Key=key)
            async with resp["Body"] as stream:
                return await stream.read()

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        async with self._client() as client:
            resp = await client.get_object(Bucket=self._bucket, Key=key)
            async with resp["Body"] as stream:
                while chunk := await stream.read(65536):
                    yield chunk

    async def delete(self, key: str) -> None:
        async with self._client() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        async with self._client() as client:
            try:
                await client.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "404":
                    return False
                raise

    async def list(self, prefix: str = "") -> list[str]:
        async with self._client() as client:
            keys: list[str] = []
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
            return keys