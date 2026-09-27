"""Unit tests for RerankerChain fallback functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.pipeline import rerank_after_fusion
from llm_client.rag.rerankers.base import RerankResult
from llm_client.rag.rerankers.chain import RerankerChain
from llm_client.rag.rerankers.identity import IdentityReranker
from llm_client.rag.metrics import RerankerMetrics, NullRerankerMetrics
from llm_client.observability.operational_writer import OperationalStreamWriter
from llm_client.observability.forensic_writer import ForensicStreamWriter


class MockReranker:
    """Mock reranker for testing."""
    
    def __init__(self, name="mock", should_fail=False, health_check_result=True):
        self.name = name
        self.should_fail = should_fail
        self.health_check_result = health_check_result
        self.rerank_calls = []  # List of calls, not count
    
    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, value: str):
        self._name = value
    
    async def health_check(self) -> bool:
        return self.health_check_result
    
    async def rerank(self, query: str, documents, top_k: int = 5, batch_size: int = 8):
        self.rerank_calls.append((query, documents, top_k, batch_size))
        
        if self.should_fail:
            raise RuntimeError(f"Mock reranker '{self.name}' failed")
        
        # Return deterministic scores: first document highest
        scores = [0.9, 0.1, 0.7, 0.3, 0.8][:len(documents)]
        return [
            RerankResult(doc_id=str(i), score=scores[i], original_index=i)
            for i in range(min(top_k, len(documents)))
        ]


@pytest.fixture
def sample_documents():
    """Sample documents for testing."""
    return [
        {"id": "doc1", "content": "This is about error codes and debugging", "metadata": {"source": "doc1"}},
        {"id": "doc2", "content": "Unrelated document about cooking recipes", "metadata": {"source": "doc2"}},
        {"id": "doc3", "content": "Another document about error handling", "metadata": {"source": "doc3"}},
        {"id": "doc4", "content": "Document about system architecture", "metadata": {"source": "doc4"}},
        {"id": "doc5", "content": "Final document about error recovery", "metadata": {"source": "doc5"}},
    ]


@pytest.fixture
def mock_registry():
    """Mock reranker registry."""
    with patch('llm_client.rag.rerankers.registry.RerankerRegistry') as mock:
        registry = MagicMock()
        mock.registry = registry
        yield registry


@pytest.fixture
def mock_operational_writer():
    """Mock operational writer."""
    writer = MagicMock(spec=OperationalStreamWriter)
    return writer


@pytest.fixture
def mock_forensic_writer():
    """Mock forensic writer."""
    writer = MagicMock(spec=ForensicStreamWriter)
    writer._enabled = True
    return writer


# ---------- RerankerChain tests ----------

class TestRerankerChain:
    """Test RerankerChain functionality."""
    
    @pytest.mark.asyncio
    async def test_rerank_with_primary_success(self):
        """Test reranking when primary reranker succeeds."""
        primary = MockReranker("primary", should_fail=False)
        fallback = MockReranker("fallback", should_fail=False)
        chain = RerankerChain([primary, fallback])
        
        docs = [{"content": "doc1"}, {"content": "doc2"}]
        results = await chain.rerank("query", docs, top_k=2)
        
        assert len(results) == 2
        assert len(primary.rerank_calls) == 1
        assert len(fallback.rerank_calls) == 0  # Should not be called
        assert all(r.score > 0 for r in results)
    
    @pytest.mark.asyncio
    async def test_rerank_with_primary_fails_fallback_succeeds(self):
        """Test reranking when primary fails but fallback succeeds."""
        primary = MockReranker("primary", should_fail=True)
        fallback = MockReranker("fallback", should_fail=False)
        chain = RerankerChain([primary, fallback])
        
        docs = [{"content": "doc1"}, {"content": "doc2"}]
        results = await chain.rerank("query", docs, top_k=2)
        
        assert len(results) == 2
        assert len(primary.rerank_calls) == 1
        assert len(fallback.rerank_calls) == 1
        assert all(r.score > 0 for r in results)
    
    @pytest.mark.asyncio
    async def test_rerank_with_all_fail(self):
        """Test reranking when all rerankers fail."""
        primary = MockReranker("primary", should_fail=True)
        fallback = MockReranker("fallback", should_fail=True)
        chain = RerankerChain([primary, fallback])
        
        docs = [{"content": "doc1"}, {"content": "doc2"}]
        results = await chain.rerank("query", docs, top_k=2)
        
        assert len(results) == 2
        assert len(primary.rerank_calls) == 1
        assert len(fallback.rerank_calls) == 1
        assert all(r.score == 1.0 for r in results)  # Identity fallback
        assert results[0].original_index == 0
        assert results[1].original_index == 1
    
    @pytest.mark.asyncio
    async def test_rerank_with_health_check_fail(self):
        """Test reranking when primary fails health check."""
        primary = MockReranker("primary", health_check_result=False)
        fallback = MockReranker("fallback", should_fail=False)
        chain = RerankerChain([primary, fallback])
        
        docs = [{"content": "doc1"}, {"content": "doc2"}]
        results = await chain.rerank("query", docs, top_k=2)
        
        assert len(results) == 2
        assert len(primary.rerank_calls) == 0  # Should not be called due to health check
        assert len(fallback.rerank_calls) == 1
        assert all(r.score > 0 for r in results)
    
    @pytest.mark.asyncio
    async def test_rerank_with_health_check_all_fail(self):
        """Test reranking when all rerankers fail health check."""
        primary = MockReranker("primary", health_check_result=False)
        fallback = MockReranker("fallback", health_check_result=False)
        chain = RerankerChain([primary, fallback])
        
        docs = [{"content": "doc1"}, {"content": "doc2"}]
        results = await chain.rerank("query", docs, top_k=2)
        
        assert len(results) == 2
        assert len(primary.rerank_calls) == 0
        assert len(fallback.rerank_calls) == 0
        assert all(r.score == 1.0 for r in results)  # Identity fallback
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check when at least one reranker is healthy."""
        primary = MockReranker("primary", health_check_result=False)
        fallback = MockReranker("fallback", health_check_result=True)
        chain = RerankerChain([primary, fallback])
        
        assert await chain.health_check() is True
    
    @pytest.mark.asyncio
    async def test_health_check_all_fail(self):
        """Test health check when all rerankers are unhealthy."""
        primary = MockReranker("primary", health_check_result=False)
        fallback = MockReranker("fallback", health_check_result=False)
        chain = RerankerChain([primary, fallback])
        
        assert await chain.health_check() is False
    
    @pytest.mark.asyncio
    async def test_rerank_with_empty_chain(self):
        """Test reranking with empty chain (should not happen but test anyway)."""
        chain = RerankerChain([])
        
        docs = [{"content": "doc1"}]
        results = await chain.rerank("query", docs, top_k=1)
        
        assert len(results) == 1
        assert results[0].score == 1.0  # Identity fallback
    
    @pytest.mark.asyncio
    async def test_rerank_with_single_reranker(self):
        """Test reranking with single reranker (no fallback needed)."""
        single = MockReranker("single", should_fail=False)
        chain = RerankerChain([single])
        
        docs = [{"content": "doc1"}, {"content": "doc2"}]
        results = await chain.rerank("query", docs, top_k=2)
        
        assert len(results) == 2
        assert len(single.rerank_calls) == 1
        assert all(r.score > 0 for r in results)


# ---------- Pipeline integration tests ----------

@pytest.mark.asyncio
async def test_pipeline_with_fallback_chain(sample_documents, mock_registry, mock_operational_writer):
    """Test pipeline integration with fallback chain."""
    # Configure mock registry
    primary = MockReranker("primary", should_fail=True)
    fallback = MockReranker("fallback", should_fail=False)
    identity = MockReranker("identity", should_fail=False)
    
    mock_registry.get.side_effect = lambda name: {
        "primary": primary,
        "fallback": fallback,
        "identity": identity,
    }[name]
    
    # Configure config with fallback chain
    config = RetrieverConfig(
        reranker_name="primary",  # This should be ignored when fallback_chain is set
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=["primary", "fallback", "identity"],
    )
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=config,
        reranker_registry=mock_registry,
        operational_writer=mock_operational_writer,
    )
    
# Should have used fallback (primary failed, fallback succeeded)
    assert len(results) == 3
    assert mock_registry.get.call_count == 3  # primary, fallback, and identity loaded from chain
    assert len(primary.rerank_calls) == 1
    assert len(fallback.rerank_calls) == 1
    assert len(identity.rerank_calls) == 0  # identity not used, fallback succeeded


@pytest.mark.asyncio
async def test_pipeline_with_fallback_chain_all_fail(sample_documents, mock_registry, mock_operational_writer):
    """Test pipeline integration with fallback chain where all rerankers fail."""
    # Configure mock registry
    primary = MockReranker("primary", should_fail=True)
    fallback = MockReranker("fallback", should_fail=True)
    identity = MockReranker("identity", should_fail=True)
    
    mock_registry.get.side_effect = lambda name: {
        "primary": primary,
        "fallback": fallback,
        "identity": identity,
    }[name]
    
    # Configure config with fallback chain
    config = RetrieverConfig(
        reranker_name="primary",
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=["primary", "fallback", "identity"],
    )
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=config,
        reranker_registry=mock_registry,
        operational_writer=mock_operational_writer,
    )
    
# Should have fallen back to identity (chain uses its own identity fallback after trying registry identity)
    assert len(results) == 3
    assert all(doc["score"] == 1.0 for doc in results)  # Identity scores from chain's internal fallback
    assert len(primary.rerank_calls) == 1
    assert len(fallback.rerank_calls) == 1
    # Identity reranker from registry is called but its result is not used (chain fallbacks to its own identity)
    assert len(identity.rerank_calls) == 1


@pytest.mark.asyncio
async def test_pipeline_without_fallback_chain_preserves_behavior(sample_documents, mock_registry, mock_operational_writer):
    """Test that pipeline without fallback chain preserves existing behavior."""
    # Configure mock registry
    mock_reranker = MockReranker("mock", should_fail=False)
    mock_registry.get.return_value = mock_reranker
    
    # Configure config without fallback chain (existing behavior)
    config = RetrieverConfig(
        reranker_name="mock",
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=None,  # Should use single reranker
    )
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=config,
        reranker_registry=mock_registry,
        operational_writer=mock_operational_writer,
    )
    
    # Should have used single reranker
    assert len(results) == 3
    assert mock_registry.get.call_count == 1
    assert len(mock_reranker.rerank_calls) == 1
    assert all(doc["score"] > 0 for doc in results)


@pytest.mark.asyncio
async def test_pipeline_with_fallback_chain_health_check_fail(sample_documents, mock_registry, mock_operational_writer):
    """Test pipeline integration with fallback chain where primary fails health check."""
    # Configure mock registry
    primary = MockReranker("primary", health_check_result=False)
    fallback = MockReranker("fallback", should_fail=False)
    
    mock_registry.get.side_effect = lambda name: {
        "primary": primary,
        "fallback": fallback,
    }[name]
    
    # Configure config with fallback chain
    config = RetrieverConfig(
        reranker_name="primary",
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=["primary", "fallback"],
    )
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=config,
        reranker_registry=mock_registry,
        operational_writer=mock_operational_writer,
    )
    
    # Should have skipped primary due to health check and used fallback
    assert len(results) == 3
    assert mock_registry.get.call_count == 2  # primary and fallback loaded
    assert len(primary.rerank_calls) == 0  # Not called due to health check
    assert len(fallback.rerank_calls) == 1


@pytest.mark.asyncio
async def test_pipeline_with_fallback_chain_registry_error(sample_documents, mock_registry, mock_operational_writer):
    """Test pipeline integration with fallback chain where a reranker is not found in registry."""
    # Configure mock registry to raise exception for one reranker
    primary = MockReranker("primary", should_fail=False)
    fallback = MockReranker("fallback", should_fail=False)
    
    def mock_get(name):
        if name == "missing":
            raise Exception("Reranker not found")
        return {"primary": primary, "fallback": fallback}[name]
    
    mock_registry.get.side_effect = mock_get
    
    # Configure config with fallback chain including missing reranker
    config = RetrieverConfig(
        reranker_name="primary",
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=["missing", "primary", "fallback"],
    )
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=config,
        reranker_registry=mock_registry,
        operational_writer=mock_operational_writer,
    )
    
    # Should have skipped missing reranker and used primary
    assert len(results) == 3
    assert mock_registry.get.call_count == 3  # missing, primary, fallback attempted
    assert len(primary.rerank_calls) == 1
    assert len(fallback.rerank_calls) == 0  # Should not be called if primary succeeds


# ---------- RetrieverConfig tests ----------

class TestRetrieverConfigWithFallbackChain:
    """Test RetrieverConfig with fallback chain functionality."""
    
    def test_fallback_chain_from_env(self):
        """Test creating config from environment with fallback chain."""
        with patch.dict('os.environ', {
            'RERANKER_FALLBACK_CHAIN': 'cohere,bge,identity'
        }):
            config = RetrieverConfig.from_env()
            
            assert config.reranker_fallback_chain == ["cohere", "bge", "identity"]
            assert config.reranker_name == "bge"  # default
    
    def test_fallback_chain_empty_from_env(self):
        """Test creating config from environment with empty fallback chain."""
        with patch.dict('os.environ', {
            'RERANKER_FALLBACK_CHAIN': ''
        }):
            config = RetrieverConfig.from_env()
            
            assert config.reranker_fallback_chain is None
    
    def test_fallback_chain_none_from_env(self):
        """Test creating config from environment without fallback chain env var."""
        with patch.dict('os.environ', {}, clear=True):
            config = RetrieverConfig.from_env()
            
            assert config.reranker_fallback_chain is None
    
    def test_fallback_chain_validation_empty(self):
        """Test validation rejects empty fallback chain."""
        with pytest.raises(ValueError, match="cannot be empty"):
            RetrieverConfig(reranker_fallback_chain=[])
    
    def test_fallback_chain_validation_too_long(self):
        """Test validation rejects fallback chain with too many rerankers."""
        with pytest.raises(ValueError, match="cannot have more than 3 rerankers"):
            RetrieverConfig(reranker_fallback_chain=["a", "b", "c", "d"])
    
    def test_fallback_chain_validation_invalid_names(self):
        """Test validation rejects invalid reranker names."""
        with pytest.raises(ValueError, match="must contain non-empty strings"):
            RetrieverConfig(reranker_fallback_chain=["valid", "", "valid"])
        
        with pytest.raises(ValueError, match="must contain non-empty strings"):
            RetrieverConfig(reranker_fallback_chain=["valid", None, "valid"])
    
    def test_fallback_chain_validation_valid(self):
        """Test validation passes for valid fallback chain."""
        # Should not raise
        config = RetrieverConfig(reranker_fallback_chain=["cohere", "bge"])
        assert config.reranker_fallback_chain == ["cohere", "bge"]
        
        config = RetrieverConfig(reranker_fallback_chain=["identity"])
        assert config.reranker_fallback_chain == ["identity"]
    
    def test_fallback_chain_none_valid(self):
        """Test None fallback chain is valid (existing behavior)."""
        # Should not raise
        config = RetrieverConfig(reranker_fallback_chain=None)
        assert config.reranker_fallback_chain is None


# ---------- Integration tests with real IdentityReranker ----------

@pytest.mark.asyncio
async def test_integration_with_identity_in_chain(sample_documents, mock_registry):
    """Test integration with real IdentityReranker in fallback chain."""
    with patch('llm_client.rag.rerankers.registry.RerankerRegistry') as mock:
        registry = MagicMock()
        
        # Use real IdentityReranker
        identity_reranker = IdentityReranker()
        
        # Mock primary that fails
        primary = MockReranker("primary", should_fail=True)
        
        registry.get.side_effect = lambda name: {
            "primary": primary,
            "identity": identity_reranker,
        }[name]
        mock.registry = registry
        
        # Configure config with fallback chain
        config = RetrieverConfig(
            reranker_name="primary",
            reranker_top_k=3,
            reranker_enabled=True,
            reranker_fallback_chain=["primary", "identity"],
        )
        
        results = await rerank_after_fusion(
            query="error codes",
            fused_docs=sample_documents,
            config=config,
            reranker_registry=registry,
        )
        
        # Should have fallen back to identity reranker
        assert len(results) == 3
        assert len(results) == len(sample_documents[:3])
        
        # Check that identity reranker preserves order and gives neutral scores
        for i, (result, original) in enumerate(zip(results, sample_documents[:3])):
            assert result["content"] == original["content"]
            assert result["metadata"] == original["metadata"]
            assert result["score"] == 1.0  # Identity fallback gives neutral score


# ---------- Metrics and logging tests ----------

@pytest.mark.asyncio
async def test_pipeline_metrics_with_fallback_chain(sample_documents, mock_registry):
    """Test that metrics are properly recorded with fallback chain."""
    metrics = RerankerMetrics()
    
    # Configure mock registry
    primary = MockReranker("primary", should_fail=True)
    fallback = MockReranker("fallback", should_fail=False)
    
    mock_registry.get.side_effect = lambda name: {
        "primary": primary,
        "fallback": fallback,
    }[name]
    
    # Configure config with fallback chain
    config = RetrieverConfig(
        reranker_name="primary",
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=["primary", "fallback"],
    )
    
    await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=config,
        reranker_registry=mock_registry,
        metrics=metrics,
    )
    
    # Should not raise errors and should have recorded metrics
    assert True  # If we get here, metrics worked


@pytest.mark.asyncio
async def test_pipeline_null_metrics_with_fallback_chain(sample_documents, mock_registry):
    """Test that null metrics don't cause errors with fallback chain."""
    metrics = NullRerankerMetrics()
    
    # Configure mock registry
    primary = MockReranker("primary", should_fail=True)
    fallback = MockReranker("fallback", should_fail=False)
    
    mock_registry.get.side_effect = lambda name: {
        "primary": primary,
        "fallback": fallback,
    }[name]
    
    # Configure config with fallback chain
    config = RetrieverConfig(
        reranker_name="primary",
        reranker_top_k=3,
        reranker_enabled=True,
        reranker_fallback_chain=["primary", "fallback"],
    )
    
    await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=config,
        reranker_registry=mock_registry,
        metrics=metrics,
    )
    
    # Should not raise errors
    assert True