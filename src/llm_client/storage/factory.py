from .base import FileStorage
from .local import LocalFileStorage
from .s3 import S3CompatibleStorage


def create_file_storage(backend: str | None = None) -> FileStorage:
    """Factory for FileStorage. Backend chosen via STORAGE_BACKEND env var.

    - "local" → LocalFileStorage (MVP fallback, backward compat).
    - "s3"    → S3CompatibleStorage (MinIO in dev, AWS S3 in prod).
    - default → "local".
    """
    import os

    backend = backend or os.getenv("STORAGE_BACKEND", "local")
    if backend == "s3":
        return S3CompatibleStorage()
    return LocalFileStorage()


__all__ = [
    "FileStorage",
    "LocalFileStorage",
    "S3CompatibleStorage",
    "create_file_storage",
]