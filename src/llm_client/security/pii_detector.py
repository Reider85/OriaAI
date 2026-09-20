"""PIIDetector — PII detection via Microsoft Presidio + custom regex recognizers (ADR-014, D-1).

Detects PERSON, EMAIL, PHONE, CREDIT_CARD, IBAN, IP, US_SSN, URL plus custom
internal formats (EMPLOYEE_ID, PROJECT_CODE). `mask()` replaces every found PII
occurrence with ``[{entity_type}]``.

Two operational modes:
  * enabled=True  — runs Presidio AnalyzerEngine (spaCy model configured via
                    ``PII_DETECTOR_SPACY_MODEL`), cached in ``__init__``.
  * enabled=False — no-op fast path used in dev/test where Presidio is not
                    required (``PII_DETECTOR_ENABLED=false``).

Notes:
  * The AnalyzerEngine is built with an explicit NlpEngineProvider that binds
    ``en_core_web_md`` — this avoids Presidio auto-downloading the ~400 MB
    ``en_core_web_lg`` default model.
  * PII text is never logged here; only types and spans are surfaced.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PIIEntity:
    """A single PII occurrence. Positions are character offsets in the input text."""

    type: str
    start: int
    end: int


@dataclass(frozen=True)
class PIIDetectionResult:
    """Result of PII analysis: score in [0,1] plus typed entity spans."""

    score: float
    entities: list[PIIEntity] = field(default_factory=list)


# Entity type -> mask label used by ``mask()``.
ENTITY_LABELS: dict[str, str] = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "CREDIT_CARD": "CREDIT_CARD",
    "IBAN_CODE": "IBAN",
    "IP_ADDRESS": "IP_ADDRESS",
    "US_SSN": "US_SSN",
    "URL": "URL",
    "EMPLOYEE_ID": "EMPLOYEE_ID",
    "PROJECT_CODE": "PROJECT_CODE",
}

class PIIDetector:
    """Detect and mask PII using Presidio + custom regex recognizers."""

    def __init__(
        self,
        spacy_model: str = "en_core_web_md",
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._spacy_model = spacy_model
        if not enabled:
            logger.info("PIIDetector disabled — detect/mask are no-ops")
            return

        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        nlp_config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": spacy_model}],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()

        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp_engine)

        registry.add_recognizer(
            PatternRecognizer(
                supported_entity="EMPLOYEE_ID",
                name="EmployeeIdRecognizer",
                patterns=[Pattern(name="employee_id", regex=r"\bEMP-\d{6}\b", score=0.9)],
                supported_language="en",
            )
        )
        registry.add_recognizer(
            PatternRecognizer(
                supported_entity="PROJECT_CODE",
                name="ProjectCodeRecognizer",
                patterns=[Pattern(name="project_code", regex=r"\bPRJ-[A-Z]{3}-\d{4}\b", score=0.9)],
                supported_language="en",
            )
        )

        # Only the allow-listed recognizer types are reported (filters out noisy
        # DATE_TIME / LOCATION matches that Presidio would otherwise surface).
        self._recognizer_types: set[str] = set(ENTITY_LABELS)
        self._engine = AnalyzerEngine(
            nlp_engine=nlp_engine,
            registry=registry,
            supported_languages=["en"],
        )
        logger.debug("PIIDetector initialized with spaCy model %s", spacy_model)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def detect(self, text: str) -> PIIDetectionResult:
        """Return PII score in [0,1] plus typed entity spans found in ``text``."""
        if not self._enabled or not text:
            return PIIDetectionResult(score=0.0, entities=[])

        results = self._engine.analyze(text=text, language="en")
        entities = self._dedupe(
            [
                PIIEntity(type=e.entity_type, start=e.start, end=e.end)
                for e in results
                if e.entity_type in self._recognizer_types
            ]
        )
        total = len(text)
        pii_chars = sum(e.end - e.start for e in entities)
        score = (pii_chars / total) if total else 0.0
        return PIIDetectionResult(score=score, entities=entities)

    def mask(self, text: str) -> str:
        """Replace every PII occurrence with ``[{type}]``. Returns text unchanged if disabled."""
        if not self._enabled or not text:
            return text

        result = self.detect(text)
        # Rebuild right-to-left so earlier spans keep their original offsets.
        masked = text
        for entity in sorted(result.entities, key=lambda e: e.start, reverse=True):
            label = ENTITY_LABELS.get(entity.type, entity.type)
            masked = masked[: entity.start] + f"[{label}]" + masked[entity.end :]
        return masked

    @staticmethod
    def _dedupe(entities: list[PIIEntity]) -> list[PIIEntity]:
        """Drop entities that fully overlap a longer one (Presidio can double-report)."""
        ordered = sorted(entities, key=lambda e: (e.start, -(e.end - e.start)))
        kept: list[PIIEntity] = []
        for entity in ordered:
            if any(e.start <= entity.start and entity.end <= e.end for e in kept):
                continue
            kept.append(entity)
        return kept