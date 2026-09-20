import pytest

from llm_client.config import Settings
from llm_client.security.pii_detector import PIIDetector
from llm_client.security.pii_metadata import attach_pii_metadata


@pytest.fixture(scope="module")
def detector():
    return PIIDetector(spacy_model="en_core_web_md", enabled=True)


def test_attach_returns_score_and_entities(detector):
    meta = attach_pii_metadata(detector, "email john@example.com", enabled=True)
    assert meta.pii_score is not None
    assert 0.0 < meta.pii_score <= 1.0
    assert meta.pii_entities
    # Only types/positions, never the PII text itself.
    for entity in meta.pii_entities:
        assert set(entity.keys()) == {"type", "start", "end"}


def test_attach_disabled_returns_nulls(detector):
    meta = attach_pii_metadata(detector, "email john@example.com", enabled=False)
    assert meta.pii_score is None
    assert meta.pii_entities is None


def test_attach_empty_content_returns_nulls(detector):
    meta = attach_pii_metadata(detector, "", enabled=True)
    assert meta.pii_score is None
    assert meta.pii_entities is None


def test_attach_disabled_detector_returns_nulls():
    det = PIIDetector(spacy_model="en_core_web_md", enabled=False)
    meta = attach_pii_metadata(det, "john@example.com", enabled=True)
    assert meta.pii_score is None
    assert meta.pii_entities is None


def test_attach_no_pii_scores_zero(detector):
    meta = attach_pii_metadata(detector, "fully benign sentence here", enabled=True)
    assert meta.pii_score == 0.0
    assert meta.pii_entities == []


def test_settings_defaults():
    s = Settings(environment="dev")
    assert s.forensic_stream_enabled is False
    assert s.pii_metadata_enabled is True
    assert s.pii_detector_spacy_model == "en_core_web_md"
    assert s.operational_log_sink == "stdout"
    assert s.kms_provider == "vault"


def test_settings_rejects_bad_environment():
    with pytest.raises(ValueError):
        Settings(environment="weird")


def test_settings_rejects_prod_without_forensic():
    with pytest.raises(ValueError):
        Settings(environment="prod", forensic_stream_enabled=False)


def test_settings_allows_staging_forensic_off():
    Settings(environment="staging", forensic_stream_enabled=False)


def test_settings_allows_prod_forensic_on():
    Settings(environment="prod", forensic_stream_enabled=True)


def test_settings_rejects_bad_sink():
    with pytest.raises(ValueError):
        Settings(environment="dev", operational_log_sink="syslog")


def test_settings_rejects_bad_kms():
    with pytest.raises(ValueError):
        Settings(environment="dev", kms_provider="fake")