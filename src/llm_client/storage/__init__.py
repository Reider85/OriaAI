"""FileStorage port & adapters (extended ADR-008, Quick Win B-2)."""

from .base import FileStorage
from .local import LocalFileStorage
from .s3 import S3CompatibleStorage

__all__ = [
    "FileStorage",
    "LocalFileStorage",
    "S3CompatibleStorage",
]