"""Unit tests for Tavily configuration validation in Settings."""

import pytest

from llm_client.config import Settings


def test_settings_tavily_api_url_default():
    """Test that tavily_api_url has the correct default."""
    settings = Settings()
    assert settings.tavily_api_url == "https://api.tavily.com/search"


def test_settings_tavily_api_url_validation():
    """Test that empty tavily_api_url raises ValueError."""
    with pytest.raises(ValueError, match="TAVILY_API_URL must be non-empty"):
        Settings(tavily_api_url="")


def test_settings_tools_enabled_default():
    """Test that tools_enabled defaults to expected list."""
    settings = Settings()
    assert settings.tools_enabled == ["file_export", "web_search", "rag_query"]


def test_settings_tools_enabled_env_parsing_comma():
    """Test parsing comma-separated TOOLS_ENABLED from env."""
    import os
    os.environ["TOOLS_ENABLED"] = "file_export,web_search"
    
    try:
        settings = Settings()
        assert settings.tools_enabled == ["file_export", "web_search"]
    finally:
        os.environ.pop("TOOLS_ENABLED")


def test_settings_tools_enabled_env_parsing_json():
    """Test parsing JSON TOOLS_ENABLED from env."""
    import os
    os.environ["TOOLS_ENABLED"] = '["file_export", "rag_query"]'
    
    try:
        settings = Settings()
        assert settings.tools_enabled == ["file_export", "rag_query"]
    finally:
        os.environ.pop("TOOLS_ENABLED")


def test_settings_tools_enabled_empty():
    """Test empty TOOLS_ENABLED from env."""
    import os
    os.environ["TOOLS_ENABLED"] = ""
    
    try:
        settings = Settings()
        assert settings.tools_enabled == []
    finally:
        os.environ.pop("TOOLS_ENABLED")


def test_settings_tavily_key_validation_web_search_enabled():
    """Test that TAVILY_API_KEY is required when web_search is in tools_enabled."""
    # Default tools_enabled includes web_search - should fail
    with pytest.raises(ValueError, match="TAVILY_API_KEY required when tools_enabled contains 'web_search'"):
        Settings(tavily_api_key="")
    
    # Explicitly enable web_search - should fail
    with pytest.raises(ValueError, match="TAVILY_API_KEY required when tools_enabled contains 'web_search'"):
        Settings(tools_enabled="web_search", tavily_api_key="")
    
    # With web_search and key set - should pass
    settings = Settings(tools_enabled="web_search", tavily_api_key="test-key")
    assert settings.tools_enabled == ["web_search"]
    assert settings.tavily_api_key == "test-key"


def test_settings_tavily_key_validation_web_search_disabled():
    """Test that TAVILY_API_KEY is not required when web_search is not in tools_enabled."""
    # Empty tools_enabled - should pass
    settings = Settings(tools_enabled="", tavily_api_key="")
    assert settings.tools_enabled == []
    assert settings.tavily_api_key == ""
    
    # Other tools only - should pass
    settings = Settings(tools_enabled="file_export,rag_query", tavily_api_key="")
    assert settings.tools_enabled == ["file_export", "rag_query"]
    assert settings.tavily_api_key == ""


def test_settings_tools_enabled_invalid_type():
    """Test that invalid tools_enabled type raises ValueError."""
    # Test that our validator catches non-list types after parsing
    settings = Settings(tools_enabled="valid")
    # Simulate invalid type after parsing
    settings.tools_enabled = 123
    with pytest.raises(TypeError, match="TOOLS_ENABLED must be a list"):
        settings._validate_environment()


def test_settings_tavily_key_validation_with_other_tools():
    """Test TAVILY_API_KEY validation with mixed tool sets."""
    # web_search not present - should pass
    settings = Settings(tools_enabled="file_export,rag_query", tavily_api_key="")
    assert settings.tools_enabled == ["file_export", "rag_query"]
    
    # web_search present with key - should pass
    settings = Settings(tools_enabled="file_export,web_search,rag_query", tavily_api_key="test-key")
    assert settings.tools_enabled == ["file_export", "web_search", "rag_query"]
    assert settings.tavily_api_key == "test-key"