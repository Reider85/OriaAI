from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import BinaryIO


class FileStorage(ABC):
    """Port for file storage operations.

    Implementation: S3CompatibleStorage (MinIO in dev, AWS S3 in prod).
    """

    @abstractmethod
    async def save(self, file: bytes | BinaryIO, key: str) -> str:
        """Save file bytes under the given key. Returns the key."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve file bytes for the given key."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete file at the given key. Idempotent."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if the key exists."""

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        """Streaming read. Default implementation buffers via get()."""
        data = await self.get(key)
        if data:
            yield data

    async def list(self, prefix: str = "") -> list[str]:
        """List keys under an optional prefix."""
        raise NotImplementedError