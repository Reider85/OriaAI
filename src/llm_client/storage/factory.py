from .base import FileStorage
from .s3 import S3CompatibleStorage


def create_file_storage() -> FileStorage:
    """Factory for FileStorage. Extended ADR-008: S3-only.

    Returns S3CompatibleStorage (MinIO in dev, AWS S3 in prod) — the sole
    FileStorage backend since Block E removed the local fallback.
    """
    return S3CompatibleStorage()


__all__ = [
    "FileStorage",
    "S3CompatibleStorage",
    "create_file_storage",
]