"""Unit tests for pipeline_singleton tiered caching and contextvar support."""

from unittest.mock import MagicMock, patch

import pytest

from llm_client.config import Settings
from llm_client.rag.config import RetrieverConfig
from llm_client.rag import pipeline_singleton
from llm_client.rag.pipeline_singleton import (
    _override_cache,
    _pipeline_cache_key,
    close_shared_pipeline,
    get_pipeline_for_request,
    get_rag_request_overrides,
    get_shared_pipeline,
    reset_rag_request_overrides,
    set_rag_request_overrides,
)
from llm_client.rag.pipeline import RagPipeline


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    return Settings(
        vector_store_kind="none",
        database_url="postgresql://test",
        openai_api_key="test-key",
    )


@pytest.fixture
def mock_pg_pool():
    """Mock asyncpg pool."""
    pool = MagicMock()
    pool.is_closed.return_value = False
    return pool


@pytest.fixture
def mock_retriever_config():
    """Mock RetrieverConfig."""
    return RetrieverConfig(
        retrieval_strategy="hybrid",
        reranker_name="bge",
        reranker_top_k=5,
        reranker_enabled=True,
    )


@pytest.fixture
def override_cache_reset():
    """Fixture to reset override cache between tests."""
    original_cache = _override_cache.copy()
    _override_cache.clear()
    yield
    _override_cache.clear()
    _override_cache.update(original_cache)


class TestPipelineCacheKey:
    """Test cache key generation."""

    def test_cache_key_from_config(self, mock_retriever_config):
        """Test cache key generation from RetrieverConfig."""
        key = _pipeline_cache_key(mock_retriever_config)
        expected = (
            "hybrid",
            "bge",
            5,
            True,
        )
        assert key == expected

    def test_cache_key_from_dict_like(self):
        """Test cache key generation from dict-like object."""
        class MockConfig:
            def __init__(self):
                self.retrieval_strategy = "vector"
                self.reranker_name = "cohere"
                self.reranker_top_k = 10
                self.reranker_enabled = False

        config = MockConfig()
        key = _pipeline_cache_key(config)
        expected = (
            "vector",
            "cohere",
            10,
            False,
        )
        assert key == expected

    def test_cache_key_with_enum_strategy(self, mock_retriever_config):
        """Test cache key with enum-style retrieval_strategy."""
        # Simulate enum with .value attribute
        original_strategy = mock_retriever_config.retrieval_strategy
        mock_retriever_config.retrieval_strategy = type("Enum", (), {"value": "bm25"})()
        
        key = _pipeline_cache_key(mock_retriever_config)
        expected = (
            "bm25",
            "bge",
            5,
            True,
        )
        assert key == expected
        
        # Restore original
        mock_retriever_config.retrieval_strategy = original_strategy


class TestGetPipelineForRequest:
    """Test tiered pipeline lookup with caching."""

    @pytest.mark.asyncio
    async def test_no_override_with_singleton(self, mock_settings, override_cache_reset):
        """Test no overrides returns singleton when it exists."""
        # Create singleton first, mocking the database pool
        with patch('llm_client.rag.pool.get_shared_pool') as mock_pool:
            mock_pool.return_value = MagicMock()
            singleton = await get_shared_pipeline(mock_settings)
            assert singleton is not None
        
        # Now test no overrides case
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            pipeline = await get_pipeline_for_request(mock_settings, None)
            
            # Should return singleton, not build new one
            assert pipeline is singleton
            mock_build.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_override_no_singleton(self, mock_settings, override_cache_reset):
        """Test no overrides with no singleton returns minimal pipeline."""
        # Clear singleton
        close_shared_pipeline()
        
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            with patch('llm_client.rag.pipeline_singleton._create_fallback_pipeline') as mock_fallback:
                fallback = mock_fallback.return_value
                pipeline = await get_pipeline_for_request(mock_settings, None)
                
                # Should fallback to minimal pipeline
                assert pipeline is fallback
                mock_build.assert_not_called()

    @pytest.mark.asyncio
    async def test_override_cache_miss(self, mock_settings, mock_pg_pool, override_cache_reset):
        """Test first override request builds and caches."""
        request_settings = {"retrieval_strategy": "vector", "reranker": "bge", "top_k": 10}
        
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_retriever = MagicMock()
            mock_build.return_value = mock_retriever
            
            with patch('llm_client.rag.pipeline_singleton._get_fallback_registry') as mock_registry:
                mock_registry.return_value = MagicMock()
                
                with patch('llm_client.rag.pipeline_singleton.RagPipeline') as mock_pipeline_class:
                    mock_pipeline = MagicMock()
                    mock_pipeline_class.return_value = mock_pipeline
                
                pipeline = await get_pipeline_for_request(mock_settings, request_settings, mock_pg_pool)
                
                # Should build new pipeline
                assert pipeline is mock_pipeline
                mock_build.assert_called_once()
                assert len(_override_cache) == 1

    @pytest.mark.asyncio
    async def test_override_cache_hit(self, mock_settings, mock_pg_pool, override_cache_reset):
        """Test second request with same overrides hits cache."""
        request_settings = {"retrieval_strategy": "vector", "reranker": "bge", "top_k": 10}
        
        # Build and cache first
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_retriever = MagicMock()
            mock_build.return_value = mock_retriever
            
            with patch('llm_client.rag.pipeline_singleton._get_fallback_registry') as mock_registry:
                mock_registry.return_value = MagicMock()
                
                with patch('llm_client.rag.pipeline_singleton.RagPipeline') as mock_pipeline_class:
                    mock_pipeline = MagicMock()
                    mock_pipeline_class.return_value = mock_pipeline
                
                await get_pipeline_for_request(mock_settings, request_settings, mock_pg_pool)
                
                # Second call should hit cache
                pipeline = await get_pipeline_for_request(mock_settings, request_settings, mock_pg_pool)
                
                assert pipeline is mock_pipeline
                # build should only be called once (first call)
                assert mock_build.call_count == 1
                assert len(_override_cache) == 1

    @pytest.mark.asyncio
    async def test_different_override_key(self, mock_settings, mock_pg_pool, override_cache_reset):
        """Test different override keys create different pipelines."""
        request_settings1 = {"retrieval_strategy": "vector", "reranker": "bge", "top_k": 10}
        request_settings2 = {"retrieval_strategy": "hybrid", "reranker": "cohere", "top_k": 5}
        
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_retriever = MagicMock()
            mock_build.return_value = mock_retriever
            
            with patch('llm_client.rag.pipeline_singleton._get_fallback_registry') as mock_registry:
                mock_registry.return_value = MagicMock()
                
                with patch('llm_client.rag.pipeline_singleton.RagPipeline') as mock_pipeline_class:
                    mock_pipeline1 = MagicMock()
                    mock_pipeline2 = MagicMock()
                    mock_pipeline_class.side_effect = [mock_pipeline1, mock_pipeline2]
                
                # First call
                pipeline1 = await get_pipeline_for_request(mock_settings, request_settings1, mock_pg_pool)
                # Second call with different overrides
                pipeline2 = await get_pipeline_for_request(mock_settings, request_settings2, mock_pg_pool)
                
                assert pipeline1 is mock_pipeline1
                assert pipeline2 is mock_pipeline2
                # Should build twice for different keys
                assert mock_build.call_count == 2
                assert len(_override_cache) == 2

    @pytest.mark.asyncio
    async def test_override_fallback_to_singleton(self, mock_settings, override_cache_reset):
        """Test override failure falls back to singleton if available."""
        # Create singleton first
        singleton = await get_shared_pipeline(mock_settings)
        
        request_settings = {"retrieval_strategy": "vector", "reranker": "bge", "top_k": 10}
        
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_build.side_effect = RuntimeError("Build failed")
            
            pipeline = await get_pipeline_for_request(mock_settings, request_settings)
            
            # Should fallback to singleton
            assert pipeline is singleton
            mock_build.assert_called_once()

    @pytest.mark.asyncio
    async def test_override_fallback_to_minimal(self, mock_settings, override_cache_reset):
        """Test override failure with no singleton falls back to minimal pipeline."""
        # Clear singleton
        close_shared_pipeline()
        
        request_settings = {"retrieval_strategy": "vector", "reranker": "bge", "top_k": 10}
        
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_build.side_effect = RuntimeError("Build failed")
            
            with patch('llm_client.rag.pipeline_singleton._create_fallback_pipeline') as mock_fallback:
                fallback = mock_fallback.return_value
                pipeline = await get_pipeline_for_request(mock_settings, request_settings)
                
                # Should fallback to minimal pipeline
                assert pipeline is fallback

    @pytest.mark.asyncio
    async def test_pg_pool_resolution(self, mock_settings, override_cache_reset):
        """Test pg_pool resolution when not provided."""
        request_settings = {"retrieval_strategy": "vector", "reranker": "bge", "top_k": 10}
        
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_retriever = MagicMock()
            mock_build.return_value = mock_retriever
            
            with patch('llm_client.rag.pipeline_singleton._get_fallback_registry') as mock_registry:
                mock_registry.return_value = MagicMock()
                
                with patch('llm_client.rag.pipeline_singleton.RagPipeline') as mock_pipeline_class:
                    mock_pipeline = MagicMock()
                    mock_pipeline_class.return_value = mock_pipeline
                
                with patch('llm_client.rag.pipeline_singleton.resolve_pool') as mock_resolve:
                    mock_pool = MagicMock()
                    mock_resolve.return_value = mock_pool
                    
                    # Call with pg_pool=None
                    await get_pipeline_for_request(mock_settings, request_settings, None)
                    
                    # Should resolve pool
                    mock_resolve.assert_called_once_with(mock_settings)
                    mock_build.assert_called_once_with(mock_build.call_args[0][0], pg_pool=mock_pool)


class TestContextVar:
    """Test contextvar functionality for request overrides."""

    def test_contextvar_set_and_get(self):
        """Test setting and getting contextvar."""
        # Initial state should be None
        assert get_rag_request_overrides() is None
        
        # Set value
        token = set_rag_request_overrides({"retrieval_strategy": "vector"})
        
        # Get value
        overrides = get_rag_request_overrides()
        assert overrides == {"retrieval_strategy": "vector"}
        
        # Reset
        reset_rag_request_overrides(token)
        assert get_rag_request_overrides() is None

    def test_contextvar_token_reset(self):
        """Test resetting contextvar with token."""
        # Set initial value
        token1 = set_rag_request_overrides({"retrieval_strategy": "vector"})
        assert get_rag_request_overrides() == {"retrieval_strategy": "vector"}
        
        # Set new value
        token2 = set_rag_request_overrides({"retrieval_strategy": "hybrid"})
        assert get_rag_request_overrides() == {"retrieval_strategy": "hybrid"}
        
        # Reset to previous (should be vector)
        reset_rag_request_overrides(token2)
        assert get_rag_request_overrides() == {"retrieval_strategy": "vector"}
        
        # Reset to default
        reset_rag_request_overrides(token1)
        assert get_rag_request_overrides() is None


class TestCloseSharedPipeline:
    """Test close_shared_pipeline behavior."""

    def test_close_clears_singleton(self):
        """Test close clears singleton but not override cache."""
        # Set some values in the module globals
        import llm_client.rag.pipeline_singleton as ps_module
        ps_module._pipeline = "mock_pipeline"
        ps_module._pipeline_settings = "mock_settings"
        ps_module._override_cache = {"key": "mock_pipeline"}
        
        close_shared_pipeline()
        
        assert ps_module._pipeline is None
        assert ps_module._pipeline_settings is None
        assert len(ps_module._override_cache) == 0

    def test_close_safe_to_call_repeatedly(self):
        """Test close is safe to call multiple times."""
        close_shared_pipeline()
        close_shared_pipeline()  # Should not raise
        close_shared_pipeline()


class TestIntegrationWithExistingSingleton:
    """Test integration with existing singleton behavior."""

    @pytest.mark.asyncio
    async def test_singleton_creation_unaffected(self, mock_settings, override_cache_reset):
        """Test existing singleton creation still works."""
        # Create singleton
        pipeline1 = await get_shared_pipeline(mock_settings)
        assert pipeline1 is not None
        
        # Create again, should return same
        pipeline2 = await get_shared_pipeline(mock_settings)
        assert pipeline1 is pipeline2

    @pytest.mark.asyncio
    async def test_cache_key_matches_env_config(self, mock_settings, override_cache_reset):
        """Test that env config cache key matches singleton key."""
        # Create singleton with env config
        await get_shared_pipeline(mock_settings)
        
        # Get env config
        env_config = RetrieverConfig.from_env()
        env_key = _pipeline_cache_key(env_config)
        
        # Test no overrides case
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            pipeline = await get_pipeline_for_request(mock_settings, None)
            
            # Should be singleton
            assert pipeline is pipeline_singleton._pipeline
            mock_build.assert_not_called()
            assert _pipeline_cache_key(env_config) == env_key


class TestErrorHandling:
    """Test error handling in edge cases."""

    @pytest.mark.asyncio
    async def test_empty_request_settings(self, mock_settings, override_cache_reset):
        """Test empty request_settings treated as None."""
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_retriever = MagicMock()
            mock_build.return_value = mock_retriever
            
            with patch('llm_client.rag.pipeline_singleton._get_fallback_registry') as mock_registry:
                mock_registry.return_value = MagicMock()
                
                with patch('llm_client.rag.pipeline_singleton.RagPipeline') as mock_pipeline_class:
                    mock_pipeline = MagicMock()
                    mock_pipeline_class.return_value = mock_pipeline
                
                # Empty dict should be treated as None (no overrides)
                pipeline = await get_pipeline_for_request(mock_settings, {})
                
                # Should hit singleton path if singleton exists, else build
                # In this case, no singleton, so builds
                assert pipeline is mock_pipeline

    @pytest.mark.asyncio
    async def test_invalid_override_values(self, mock_settings, override_cache_reset):
        """Test invalid override values are filtered out."""
        request_settings = {
            "retrieval_strategy": "invalid_strategy",  # Should be filtered
            "reranker": "bge",
            "top_k": "not_a_number",  # Should be filtered
        }
        
        with patch('llm_client.rag.pipeline_singleton._build_retriever') as mock_build:
            mock_retriever = MagicMock()
            mock_build.return_value = mock_retriever
            
            with patch('llm_client.rag.pipeline_singleton._get_fallback_registry') as mock_registry:
                mock_registry.return_value = MagicMock()
                
                with patch('llm_client.rag.pipeline_singleton.RagPipeline') as mock_pipeline_class:
                    mock_pipeline = MagicMock()
                    mock_pipeline_class.return_value = mock_pipeline
                
                pipeline = await get_pipeline_for_request(mock_settings, request_settings)
                
                # Should build pipeline with filtered config
                assert pipeline is mock_pipeline
                assert len(_override_cache) == 1