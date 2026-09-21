"""FileStorage port & adapter (extended ADR-008, Block E)."""

from .base import FileStorage
from .s3 import S3CompatibleStorage

__all__ = [
    "FileStorage",
    "S3CompatibleStorage",
]