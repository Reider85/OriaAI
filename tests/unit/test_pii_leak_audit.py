"""F-2: Automated PII leak audit (ADR-014 ROADMAP.md §5.6 p.2).

Protects against regressions: if the operational stream masking misses a PII type,
this test FAILS with the leak type and position. The audit uses an INDEPENDENT
Presidio AnalyzerEngine (not the same engine that does masking) as ground truth.
"""

import json
from collections.abc import Iterator

import pytest

from llm_client.observability.operational_writer import OperationalStreamWriter
from llm_client.security.pii_detector import PIIEntity

# All 10 PII types the masking detector (D-1) must handle: 8 Presidio defaults +
# 2 custom regex recognizers (employee_id, project_code).
REQUIRED_PII_TYPES = {
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "US_SSN",
    "URL",
    "EMPLOYEE_ID",
    "PROJECT_CODE",
}

# (presidio_entity_type, realistic message containing that PII)
# Notes: avoid date/time phrases ("Friday", "on weekdays") — Presidio's DATE_TIME
# recognizer would flag them in the audit and cause false positives unrelated to PII.
PII_SAMPLES: list[tuple[str, str]] = [
    ("PERSON", "My name is John Doe and I work on the data platform"),
    ("EMAIL_ADDRESS", "Your mailbox john.doe@example.com is almost full"),
    ("PHONE_NUMBER", "Reach the support team at +1-202-555-0173"),
    ("CREDIT_CARD", "The card 4111 1111 1111 1111 was declined for the order"),
    ("IBAN_CODE", "Please refund the payment to SE45 5000 0000 0583 9825 7466"),
    ("IP_ADDRESS", "The service at 192.168.1.100 returned an error"),
    ("US_SSN", "The customer form lists their SSN as 123-45-6789 on file"),
    ("URL", "The onboarding docs live at https://example.com/path?q=1"),
    ("EMPLOYEE_ID", "Reporter EMP-123456 opened the incident"),
    ("PROJECT_CODE", "The release for PRJ-ABC-1234 is scheduled"),
]


class CapturingSink:
    """Buffered sink so the audit can inspect every emitted operational record."""

    def __init__(self) -> None:
        self.records: list[str] = []

    async def write_batch(self, events: list[str]) -> None:
        self.records.extend(events)


@pytest.fixture(scope="module")
def audit_analyzer():
    """Independent Presidio analyzer used as ground truth for the audit.

    Deliberately NOT the PIIDetector engine — a self-test must not use the same
    detection path it is trying to validate (Anti-pattern in F-2).
    """
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_md"}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="EMPLOYEE_ID",
            name="AuditEmployeeIdRecognizer",
            patterns=[Pattern(name="employee_id", regex=r"\bEMP-\d{6}\b", score=0.9)],
            supported_language="en",
        )
    )
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="PROJECT_CODE",
            name="AuditProjectCodeRecognizer",
            patterns=[Pattern(name="project_code", regex=r"\bPRJ-[A-Z]{3}-\d{4}\b", score=0.9)],
            supported_language="en",
        )
    )
    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry, supported_languages=["en"])


def _string_leaks(auditor, text: str) -> list[PIIEntity]:
    if not text:
        return []
    # Restrict to the declared PII type universe: Presidio's spaCy NER also emits
    # noisy ORGANIZATION/LOCATION hits on arbitrary short strings ("u-42"), which
    # are not PII under ADR-014 and would drown out genuine leaks.
    return [
        PIIEntity(type=e.entity_type, start=e.start, end=e.end)
        for e in auditor.analyze(text=text, language="en", entities=list(REQUIRED_PII_TYPES))
    ]


def _collect_leaks(auditor, records: list[str]) -> list[tuple[str, str, PIIEntity]]:
    """Walk every string value in every operational record; return raw PII leaks.

    Returns (record, context, entity) triples so a failure report keeps the PII
    *type* and *position* for debugging (F-2 anti-pattern: don't fully mask leaks).
    """
    leaks: list[tuple[str, str, PIIEntity]] = []
    for record in records:
        try:
            event = json.loads(record)
        except json.JSONDecodeError:
            continue
        for context, found in _iter_value_leaks(auditor, event, path="event"):
            leaks.append((record, context, found[0]))

    return leaks


def _iter_value_leaks(auditor, value, *, path: str) -> Iterator[tuple[str, list[PIIEntity]]]:
    if isinstance(value, str):
        found = _string_leaks(auditor, value)
        if found:
            yield path, found
    elif isinstance(value, dict):
        for key, sub in value.items():
            yield from _iter_value_leaks(auditor, sub, path=f"{path}.{key}")
    elif isinstance(value, list):
        for idx, sub in enumerate(value):
            yield from _iter_value_leaks(auditor, sub, path=f"{path}[{idx}]")


def _leak_report(leaks: list[tuple[str, str, PIIEntity]]) -> str:
    if not leaks:
        return ""
    lines = [f"{len(leaks)} PII leak(s) found in operational stream after masking:"]
    for record, context, entity in leaks:
        snippet = record[max(0, entity.start - 10) : entity.end + 10]
        lines.append(
            f"  - {entity.type} @ {context} [{entity.start}:{entity.end}] near {snippet!r}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# F-2 DoD: 0 leaks in the masked operational stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pii_leak_audit_operational_stream(pii_detector, audit_analyzer):
    sink = CapturingSink()
    writer = OperationalStreamWriter(pii_detector, sink=sink)
    for _entity_type, text in PII_SAMPLES:
        await writer.write(
            {
                "event_type": "user_message",
                "session_id": "audit-session-1",
                "user_id": "u-42",
                "content": text,
                "meta": {"note": text, "tags": ["a", text]},
            }
        )
    await writer.flush()

    assert sink.records, "operational stream emitted no records (audit cannot run)"
    leaks = _collect_leaks(audit_analyzer, sink.records)
    assert not leaks, _leak_report(leaks)


# ---------------------------------------------------------------------------
# F-2 DoD: cover all 10 PII types with test cases
# ---------------------------------------------------------------------------


def test_all_pii_types_covered_by_audit_samples():
    covered = {entity_type for entity_type, _ in PII_SAMPLES}
    missing = REQUIRED_PII_TYPES - covered
    assert not missing, f"PII test cases missing types: {sorted(missing)}"


# ---------------------------------------------------------------------------
# F-2 DoD: custom recognizers (standard Presidio does not cover them)
# ---------------------------------------------------------------------------


def test_audit_analyzer_detects_custom_entities(audit_analyzer):
    raw = "Reporter EMP-123456 filed for PRJ-ABC-1234"
    types = {e.type for e in _string_leaks(audit_analyzer, raw)}
    assert "EMPLOYEE_ID" in types
    assert "PROJECT_CODE" in types


# ---------------------------------------------------------------------------
# F-2 DoD: leak report keeps type + position (not fully masked)
# ---------------------------------------------------------------------------


def test_leak_report_includes_type_and_position():
    leaks = [
        ('{"content": "john@example.com"}', "event.content", PIIEntity("EMAIL_ADDRESS", 10, 26))
    ]
    report = _leak_report(leaks)
    assert "EMAIL_ADDRESS" in report
    assert "10:26" in report


# ---------------------------------------------------------------------------
# F-2 DoD: recursion walks nested dicts and lists
# ---------------------------------------------------------------------------


def test_collect_leaks_walks_nested_values(audit_analyzer):
    record = json.dumps({"a": {"b": ["plain", "call john@example.com now"]}, "c": "no pii"})
    leaks = _collect_leaks(audit_analyzer, [record])
    assert len(leaks) == 1
    assert leaks[0][1] == "event.a.b[1]"


# ---------------------------------------------------------------------------
# F-2 DoD: audit finds raw PII in passthrough records (self-check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_detects_untouched_pii(disabled_pii_detector, audit_analyzer):
    """The audit must be able to detect raw PII, otherwise it is toothless.

    A disabled masking detector leaves PII untouched; the audit must flag it.
    """
    sink = CapturingSink()
    writer = OperationalStreamWriter(disabled_pii_detector, sink=sink)
    await writer.write(
        {"event_type": "raw", "session_id": "s", "content": "email john@example.com"}
    )
    await writer.flush()
    leaks = _collect_leaks(audit_analyzer, sink.records)
    assert leaks, "audit analyzer must detect raw PII in unmasked output"


# ---------------------------------------------------------------------------
# F-2 DoD: masked bracket labels are not PII
# ---------------------------------------------------------------------------


def test_masked_brackets_are_not_leaked(audit_analyzer):
    assert _string_leaks(audit_analyzer, "[EMAIL] [PERSON] [PHONE]") == []
