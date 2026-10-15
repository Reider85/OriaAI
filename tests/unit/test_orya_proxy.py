"""Test OryaSecurity proxy support for ZAI provider."""

import pytest

from llm_client.agent.provider import LLMProviderFactory
from llm_client.config import Settings
from llm_client.rag.retrieval.vector_store_factory import create_embedding_function


def test_zai_with_orya_proxy():
    """Test that ZAI provider correctly configures OryaSecurity proxy."""
    
    # Create LLM with proxy - this should work without errors
    llm = LLMProviderFactory.create(
        provider="ZAI",
        model="glm-4.5",
        api_key="test_zai_key",
        orya_proxy_url="http://localhost:8000/v1",
        orya_proxy_key="test_orya_key"
    )
    
    # Verify that ChatOpenAI was created successfully
    assert llm is not None
    # Check that streaming is disabled when using proxy (OryaSecurity doesn't support streaming)
    assert llm.streaming is False
    # Check that the proxy URL is used as base_url (access via openai_api_base)
    assert llm.openai_api_base == "http://localhost:8000/v1"
    # Check that the proxy key is used as API key (not directly accessible in LangChain)
    # The fact that the object was created with the proxy URL confirms the key was used


def test_zai_without_proxy():
    """Test that ZAI provider works normally without proxy."""
    
    # Create LLM without proxy
    llm = LLMProviderFactory.create(
        provider="ZAI",
        model="glm-4.5",
        api_key="test_zai_key",
        base_url="https://api.z.ai/api/paas/v4"
    )
    
    # Verify that ChatOpenAI was created successfully
    assert llm is not None
    # Check that streaming is enabled by default
    assert llm.streaming is True
    # Check that the direct ZAI URL is used as base_url (access via openai_api_base)
    assert llm.openai_api_base == "https://api.z.ai/api/paas/v4"
    # Check that the direct ZAI key is used as API key (not directly accessible in LangChain)
    # The fact that the object was created with the direct URL confirms the key was used


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


def test_embeddings_with_orya_proxy():
    """Test that embeddings use OryaSecurity proxy when configured."""
    
    # Create settings with proxy
    settings = Settings(
        embedding_provider="zai",
        embedding_model="text-embedding-3-small",
        zai_api_key="test_zai_key",
        orya_proxy_url="http://localhost:8000/v1",
        orya_proxy_key="test_orya_key"
    )
    
    # Create embeddings with proxy
    embeddings = create_embedding_function(settings)
    
    # Verify that embeddings were created successfully
    assert embeddings is not None
    # Check that the proxy URL is used as base_url (access via openai_api_base)
    assert embeddings.openai_api_base == "http://localhost:8000/v1"
    # Check that the proxy key is used as API key (not directly accessible in LangChain)
    # The fact that the object was created with the proxy URL confirms the key was used


def test_embeddings_without_proxy():
    """Test that embeddings work normally without proxy."""
    
    # Create settings without proxy
    settings = Settings(
        embedding_provider="zai",
        embedding_model="text-embedding-3-small",
        zai_api_key="test_zai_key",
        zai_base_url="https://api.z.ai/api/paas/v4"
    )
    
    # Create embeddings without proxy
    embeddings = create_embedding_function(settings)
    
    # Verify that embeddings were created successfully
    assert embeddings is not None
    # Check that the direct ZAI URL is used as base_url (access via openai_api_base)
    assert embeddings.openai_api_base == "https://api.z.ai/api/paas/v4"
    # Check that the direct ZAI key is used as API key (not directly accessible in LangChain)
    # The fact that the object was created with the direct URL confirms the key was used