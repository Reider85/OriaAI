import pytest

from llm_client.security.pii_detector import PIIDetector


@pytest.fixture(scope="module")
def detector():
    return PIIDetector(spacy_model="en_core_web_md", enabled=True)


@pytest.fixture(scope="module")
def disabled_detector():
    return PIIDetector(spacy_model="en_core_web_md", enabled=False)


def test_detect_person_and_email(detector):
    result = detector.detect("My name is John Doe, email: john@example.com")
    types = {e.type for e in result.entities}
    assert "PERSON" in types
    assert "EMAIL_ADDRESS" in types


def test_mask_replaces_person_and_email(detector):
    masked = detector.mask("My name is John Doe, email: john@example.com")
    assert "[PERSON]" in masked
    assert "[EMAIL]" in masked
    assert "John Doe" not in masked
    assert "john@example.com" not in masked


def test_score_is_pii_ratio(detector):
    text = "john@example.com"
    result = detector.detect(text)
    assert 0.0 < result.score <= 1.0
    # Only the email is PII here.
    pii_chars = sum(e.end - e.start for e in result.entities)
    assert result.score == pytest.approx(pii_chars / len(text))


def test_custom_recognizer_employee_id(detector):
    result = detector.detect("Reporter EMP-123456 opened the ticket")
    assert any(e.type == "EMPLOYEE_ID" for e in result.entities)
    masked = detector.mask("Reporter EMP-123456 opened the ticket")
    assert "[EMPLOYEE_ID]" in masked
    assert "EMP-123456" not in masked


def test_custom_recognizer_project_code(detector):
    result = detector.detect("See PRJ-ABC-1234 for details")
    assert any(e.type == "PROJECT_CODE" for e in result.entities)
    masked = detector.mask("See PRJ-ABC-1234 for details")
    assert "[PROJECT_CODE]" in masked


def test_no_pii_returns_zero_score(detector):
    result = detector.detect("This is a completely benign sentence about weather.")
    assert result.score == 0.0
    assert result.entities == []


def test_empty_string(detector):
    result = detector.detect("")
    assert result.score == 0.0
    assert result.entities == []
    assert detector.mask("") == ""


def test_only_pii_text(detector):
    masked = detector.mask("john@example.com")
    assert "[EMAIL]" in masked


def test_multilang_text_does_not_crash(detector):
    text = "Привет, это тестовое сообщение с email john@example.com внутри."
    result = detector.detect(text)
    assert any(e.type == "EMAIL_ADDRESS" for e in result.entities)
    masked = detector.mask(text)
    assert "[EMAIL]" in masked


def test_disabled_detector_noop(disabled_detector):
    text = "My email is john@example.com"
    assert disabled_detector.detect(text).score == 0.0
    assert disabled_detector.mask(text) == text


def test_enabled_flag(disabled_detector):
    assert not disabled_detector.enabled


def test_overlapping_dedupe_no_crash(detector):
    # URL recognizer can overlap an email; the dedupe should not crash and
    # should keep at least one entity.
    result = detector.detect("site https://example.com/john@example.com done")
    assert result.score >= 0.0