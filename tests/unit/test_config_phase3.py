"""Phase 3 configuration tests — semantic cache (ADR-011)."""

import os

import pytest

from llm_client.config import Settings

# Temporarily clear REDIS_SEMANTIC_CACHE_URL to test default value
os.environ.pop("REDIS_SEMANTIC_CACHE_URL", None)


def test_redis_semantic_cache_url_default():
    """Test redis_semantic_cache_url default value."""
    # Test with default settings - when .env is present, it overrides the class default
    settings = Settings()
    # In real usage with .env, the env var takes precedence over class default
    assert settings.redis_semantic_cache_url == "redis://127.0.0.1:6380/2"


def test_semantic_cache_enabled_default_true():
    """Test semantic_cache_enabled default is True."""
    settings = Settings()
    assert settings.semantic_cache_enabled is True


def test_semantic_cache_disabled_via_env():
    """Test SEMANTIC_CACHE_ENABLED=false via env var."""
    try:
        os.environ["SEMANTIC_CACHE_ENABLED"] = "false"
        settings = Settings()
        assert settings.semantic_cache_enabled is False
    finally:
        os.environ.pop("SEMANTIC_CACHE_ENABLED", None)


def test_validate_environment_fails_when_sem_cache_url_missing():
    """Test validation fails when SEMANTIC_CACHE_ENABLED=true but REDIS_SEMANTIC_CACHE_URL is empty."""
    with pytest.raises(
        ValueError, match="REDIS_SEMANTIC_CACHE_URL must be set when SEMANTIC_CACHE_ENABLED=true"
    ):
        Settings(semantic_cache_enabled=True, redis_semantic_cache_url="")


def test_validate_environment_rejects_db0_and_db1():
    """Test validation rejects Redis DB 0 and DB 1 for semantic cache."""
    # Test DB 0
    with pytest.raises(ValueError, match="semantic cache must not use Redis DB 0"):
        Settings(semantic_cache_enabled=True, redis_semantic_cache_url="redis://127.0.0.1:6379/0")

    # Test DB 1 - pydantic v2 includes more context in error message
    with pytest.raises(ValueError, match="semantic cache must not use Redis DB 0.*DB 1"):
        Settings(semantic_cache_enabled=True, redis_semantic_cache_url="redis://127.0.0.1:6379/1")

    # Test valid DB 2
    settings = Settings(
        semantic_cache_enabled=True, redis_semantic_cache_url="redis://127.0.0.1:6379/2"
    )
    assert settings.redis_semantic_cache_url == "redis://127.0.0.1:6379/2"

    # Test valid DB 3
    settings = Settings(
        semantic_cache_enabled=True, redis_semantic_cache_url="redis://127.0.0.1:6379/3"
    )
    assert settings.redis_semantic_cache_url == "redis://127.0.0.1:6379/3"


def test_semantic_cache_disabled_no_url_validation():
    """Test no URL validation when SEMANTIC_CACHE_ENABLED=false."""
    # Empty URL should be fine when disabled
    settings = Settings(semantic_cache_enabled=False, redis_semantic_cache_url="")
    assert settings.semantic_cache_enabled is False
    assert settings.redis_semantic_cache_url == ""

    # DB 0/1 should be fine when disabled
    settings = Settings(
        semantic_cache_enabled=False, redis_semantic_cache_url="redis://127.0.0.1:6379/0"
    )
    assert settings.semantic_cache_enabled is False
