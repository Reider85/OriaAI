"""PII detection & masking (ADR-014, Block D-1, D-5)."""

from .pii_detector import PIIDetectionResult, PIIDetector, PIIEntity
from .pii_metadata import PIIScoreMetadata, attach_pii_metadata

__all__ = [
    "PIIDetectionResult",
    "PIIDetector",
    "PIIEntity",
    "PIIScoreMetadata",
    "attach_pii_metadata",
]