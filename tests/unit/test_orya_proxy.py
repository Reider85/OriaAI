"""Test OryaSecurity proxy support for ZAI provider."""

import pytest

from llm_client.agent.provider import LLMProviderFactory
from llm_client.config import Settings


def test_zai_with_orya_proxy():
    """Test that ZAI provider correctly configures OryaSecurity proxy."""
    
    # Create LLM with proxy - this should work without errors
    llm = LLMProviderFactory.create(
        provider="ZAI",
        model="glm-4.5",
        api_key="test_zai_key",
        orya_proxy_url="http://proxy.oryasecurity.internal:8443",
        orya_proxy_key="test_orya_key"
    )
    
    # Verify that ChatOpenAI was created successfully
    assert llm is not None


def test_zai_without_proxy():
    """Test that ZAI provider works normally without proxy."""
    
    # Create LLM without proxy
    llm = LLMProviderFactory.create(
        provider="ZAI",
        model="glm-4.5",
        api_key="test_zai_key"
    )
    
    # Verify that ChatOpenAI was created successfully
    assert llm is not None


def test_orya_proxy_url_validation():
    """Test OryaSecurity proxy URL validation in Settings."""
    
    # Test valid proxy URL with key
    settings = Settings(
        llm_provider="ZAI",
        zai_api_key="test_zai_key",
        orya_proxy_url="http://proxy.oryasecurity.internal:8443",
        orya_proxy_key="test_orya_key"
    )
    assert settings.orya_proxy_url == "http://proxy.oryasecurity.internal:8443"
    
    # Test valid HTTPS proxy URL with key
    settings = Settings(
        llm_provider="ZAI",
        zai_api_key="test_zai_key",
        orya_proxy_url="https://proxy.oryasecurity.internal:8443",
        orya_proxy_key="test_orya_key"
    )
    assert settings.orya_proxy_url == "https://proxy.oryasecurity.internal:8443"
    
    # Test invalid proxy URL (should raise validation error)
    with pytest.raises(ValueError, match="ORYA_PROXY_URL must start with http:// or https://"):
        Settings(
            llm_provider="ZAI",
            zai_api_key="test_zai_key",
            orya_proxy_url="ftp://invalid-proxy.com",
            orya_proxy_key="test_orya_key"
        )


def test_orya_proxy_key_validation():
    """Test OryaSecurity proxy key validation in Settings."""
    
    # Test with proxy URL but no key (should raise validation error)
    with pytest.raises(ValueError, match="ORYA_PROXY_KEY required when ORYA_PROXY_URL is set"):
        Settings(
            llm_provider="ZAI",
            zai_api_key="test_zai_key",
            orya_proxy_url="http://proxy.oryasecurity.internal:8443"
            # orya_proxy_key is missing
        )
    
    # Test with both proxy URL and key (should be valid)
    settings = Settings(
        llm_provider="ZAI",
        zai_api_key="test_zai_key",
        orya_proxy_url="http://proxy.oryasecurity.internal:8443",
        orya_proxy_key="test_orya_key"
    )
    assert settings.orya_proxy_url == "http://proxy.oryasecurity.internal:8443"
    assert settings.orya_proxy_key == "test_orya_key"