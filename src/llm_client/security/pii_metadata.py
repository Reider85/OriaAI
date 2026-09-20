"""PII score tracking for messages metadata (ADR-014, Block D-5).

The persistence layer is introduced later in the roadmap; this helper produces the
``pii_score`` / ``pii_entities`` metadata that callers persist on every message write
when ``PII_METADATA_ENABLED`` is true.

anti-pattern guards:
  * ``pii_entities`` never carries PII text — only ``{type, start, end}``.
  * scores are only computed at write time (never recomputed on read).
"""
from dataclasses import dataclass

from .pii_detector import PIIDetector


@dataclass(frozen=True)
class PIIScoreMetadata:
    """PII metadata to persist alongside a message."""

    pii_score: float | None = None
    pii_entities: list[dict] | None = None


def attach_pii_metadata(
    pii_detector: PIIDetector,
    content: str,
    *,
    enabled: bool = True,
) -> PIIScoreMetadata:
    """Compute PII metadata for ``content``; returns None-stubs when disabled.

    ``pii_entities`` contains only ``{"type", "start", "end"}`` — never the matched
    PII text itself (that would leak PII into the database).
    """
    if not enabled or not pii_detector.enabled or not content:
        return PIIScoreMetadata(pii_score=None, pii_entities=None)

    result = pii_detector.detect(content)
    entities = [
        {"type": e.type, "start": e.start, "end": e.end}
        for e in result.entities
        if e.type
        in {
            "PERSON",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "CREDIT_CARD",
            "IBAN_CODE",
            "IP_ADDRESS",
            "US_SSN",
            "URL",
        }
    ]
    return PIIScoreMetadata(
        pii_score=round(result.score, 4),
        pii_entities=entities,
    )


__all__ = ["PIIScoreMetadata", "attach_pii_metadata"]