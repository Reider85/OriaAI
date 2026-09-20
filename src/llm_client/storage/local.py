import os
import shutil
from collections.abc import AsyncIterator
from typing import BinaryIO

import aiofiles  # type: ignore[import-untyped]

from .base import FileStorage


class LocalFileStorage(FileStorage):
    """Filesystem-backed storage. MVP fallback backend (Block 2 of extended ADR-008).

    Deprecated in favor of S3CompatibleStorage — kept until full Block E migration.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir: str = base_dir or os.getenv("LOCAL_STORAGE_DIR") or "./data/files"
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe = key.lstrip("/")
        return os.path.join(self.base_dir, safe)

    async def save(self, file: bytes | BinaryIO, key: str) -> str:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = file.read() if hasattr(file, "read") else file
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return key

    async def get(self, key: str) -> bytes:
        async with aiofiles.open(self._path(key), "rb") as f:
            return await f.read()

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        async with aiofiles.open(self._path(key), "rb") as f:
            while chunk := await f.read(65536):
                yield chunk

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)

    async def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    async def list(self, prefix: str = "") -> list[str]:
        root = self.base_dir
        result: list[str] = []
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                full = os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/")
                if full.startswith(prefix):
                    result.append(full)
        return result

    def clear(self) -> None:
        if os.path.isdir(self.base_dir):
            shutil.rmtree(self.base_dir, ignore_errors=True)
            os.makedirs(self.base_dir, exist_ok=True)