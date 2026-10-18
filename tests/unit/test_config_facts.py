"""Unit tests for Phase 3 A-3 facts extraction settings."""

import pytest

from llm_client.config import Settings


def test_facts_extraction_defaults():
    """Test facts extraction settings have correct defaults."""
    s = Settings()
    assert s.facts_extraction_enabled is True
    assert s.facts_extractor_model == "gpt-4o-mini"
    assert s.facts_extraction_max_facts_per_doc == 10
    assert s.facts_embedding_model == "text-embedding-3-small"
    assert s.facts_embedding_dimension == 1536


def test_facts_extraction_disabled_via_env():
    """Test facts extraction can be disabled via environment variable."""
    s = Settings(facts_extraction_enabled=False)
    assert s.facts_extraction_enabled is False


def test_validate_environment_fails_when_facts_model_invalid():
    """Test validation fails when FACTS_EXTRACTOR_MODEL is invalid."""
    with pytest.raises(ValueError, match="FACTS_EXTRACTOR_MODEL must be gpt-4o-mini|gpt-4o|gpt-3.5-turbo"):
        Settings(facts_extraction_enabled=True, facts_extractor_model="invalid-model")


def test_validate_environment_fails_when_facts_max_facts_invalid():
    """Test validation fails when FACTS_EXTRACTION_MAX_FACTS_PER_DOC is <= 0."""
    with pytest.raises(ValueError, match="FACTS_EXTRACTION_MAX_FACTS_PER_DOC must be > 0"):
        Settings(facts_extraction_enabled=True, facts_extraction_max_facts_per_doc=0)


def test_validate_environment_fails_when_facts_embedding_model_invalid():
    """Test validation fails when FACTS_EMBEDDING_MODEL is invalid."""
    with pytest.raises(ValueError, match="FACTS_EMBEDDING_MODEL must be text-embedding-3-small|text-embedding-3-large"):
        Settings(facts_extraction_enabled=True, facts_embedding_model="invalid-model")


def test_validate_environment_fails_when_facts_dimension_invalid():
    """Test validation fails when FACTS_EMBEDDING_DIMENSION is invalid."""
    with pytest.raises(ValueError, match="FACTS_EMBEDDING_DIMENSION must be 1536|3072"):
        Settings(facts_extraction_enabled=True, facts_embedding_dimension=1024)


def test_facts_validation_skipped_when_disabled():
    """Test facts validation is skipped when facts extraction is disabled."""
    # These would fail if enabled, but should pass when disabled
    s = Settings(
        facts_extraction_enabled=False,
        facts_extractor_model="invalid-model",
        facts_extraction_max_facts_per_doc=0,
        facts_embedding_model="invalid-model",
        facts_embedding_dimension=1024,
    )
    assert s.facts_extraction_enabled is False
    assert s.facts_extractor_model == "invalid-model"
    assert s.facts_extraction_max_facts_per_doc == 0
    assert s.facts_embedding_model == "invalid-model"
    assert s.facts_embedding_dimension == 1024