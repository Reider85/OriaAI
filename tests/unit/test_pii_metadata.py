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


# ---------------------------------------------------------------------------
# D-5 DoD: migration SQL validation
# ---------------------------------------------------------------------------

def test_migration_sql_file_exists():
    """The migration file must exist at migrations/005_add_pii_score_to_messages.sql."""
    from pathlib import Path

    migration_path = Path(__file__).resolve().parent.parent.parent / "migrations" / "005_add_pii_score_to_messages.sql"
    assert migration_path.exists(), f"Migration file not found: {migration_path}"


def test_migration_sql_contains_required_statements():
    """Migration must add pii_score, pii_entities columns and create index."""
    from pathlib import Path

    migration_path = Path(__file__).resolve().parent.parent.parent / "migrations" / "005_add_pii_score_to_messages.sql"
    sql = migration_path.read_text()
    assert "pii_score" in sql.lower()
    assert "pii_entities" in sql.lower()
    assert "float" in sql.lower()
    assert "jsonb" in sql.lower()
    assert "create index" in sql.lower()
    assert "idx_messages_pii_score" in sql.lower()


def test_migration_sql_no_separate_table():
    """D-5 anti-pattern: must NOT create a separate pii_scores table."""
    from pathlib import Path

    migration_path = Path(__file__).resolve().parent.parent.parent / "migrations" / "005_add_pii_score_to_messages.sql"
    sql = migration_path.read_text().lower()
    assert "create table" not in sql, "Migration should ALTER existing table, not create a new one"


# ---------------------------------------------------------------------------
# D-5 DoD: SQL analytics query validation
# ---------------------------------------------------------------------------

def test_analytics_query_present_in_migration():
    """D-5 Task 5: analytics SQL query must be documented (in comments)."""
    from pathlib import Path

    migration_path = Path(__file__).resolve().parent.parent.parent / "migrations" / "005_add_pii_score_to_messages.sql"
    sql = migration_path.read_text()
    assert "avg(pii_score)" in sql.lower() or "AVG(pii_score)" in sql
    assert "high_pii_messages" in sql.lower() or "FILTER" in sql


# ---------------------------------------------------------------------------
# D-5 DoD: pii_entities never contains PII text
# ---------------------------------------------------------------------------

def test_pii_entities_exclude_text_field(detector):
    """D-5 anti-pattern: pii_entities must never contain matched PII text."""
    meta = attach_pii_metadata(detector, "John Doe email john@example.com", enabled=True)
    assert meta.pii_entities is not None
    for entity in meta.pii_entities:
        assert "text" not in entity, f"Entity must not contain 'text' field: {entity}"
        assert set(entity.keys()) == {"type", "start", "end"}


def test_pii_metadata_custom_recognizers_excluded():
    """D-5: custom recognizers (EMPLOYEE_ID, PROJECT_CODE) should be excluded from metadata."""
    det = PIIDetector(spacy_model="en_core_web_md", enabled=True)
    meta = attach_pii_metadata(det, "EMP-123456 opened PRJ-ABC-1234", enabled=True)
    if meta.pii_entities:
        entity_types = {e["type"] for e in meta.pii_entities}
        assert "EMPLOYEE_ID" not in entity_types
        assert "PROJECT_CODE" not in entity_types