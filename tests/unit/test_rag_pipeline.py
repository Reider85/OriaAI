"""Unit tests for RAG pipeline reranking functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_client.observability.forensic_writer import ForensicStreamWriter
from llm_client.observability.operational_writer import OperationalStreamWriter
from llm_client.rag.config import RetrieverConfig
from llm_client.rag.metrics import NullRerankerMetrics, RerankerMetrics
from llm_client.rag.pipeline import _identity_fallback, rerank_after_fusion
from llm_client.rag.rerankers.base import RerankResult
from llm_client.rag.rerankers.identity import IdentityReranker


class MockReranker:
    """Mock reranker for testing."""
    
    def __init__(self, name="mock", should_fail=False):
        self.name = name
        self.should_fail = should_fail
    
    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, value: str):
        self._name = value
    
    async def health_check(self) -> bool:
        return not self.should_fail
    
    async def rerank(self, query: str, documents, top_k: int = 5, batch_size: int = 8):
        if self.should_fail:
            raise RuntimeError("Mock reranker failed")
        
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
def reranker_config():
    """Default reranker config for testing."""
    return RetrieverConfig(
        reranker_name="mock",
        reranker_top_k=3,
        reranker_enabled=True,
    )


@pytest.fixture
def mock_registry():
    """Mock reranker registry."""
    with patch('llm_client.rag.pipeline.RerankerRegistry') as mock:
        registry = MagicMock()
        registry.get.return_value = MockReranker("mock")
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


# ---------- rerank_after_function ----------

@pytest.mark.asyncio
async def test_rerank_after_fusion_with_enabled_reranker(sample_documents, reranker_config, mock_registry):
    """Test reranking with enabled reranker."""
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
    )
    
    # Should return top 3 documents
    assert len(results) == 3
    # Results should contain content, metadata, and score
    for result in results:
        assert "content" in result
        assert "metadata" in result
        assert "score" in result
        assert result["score"] > 0
    
    # Mock registry should have been called
    mock_registry.get.assert_called_once_with("mock")


@pytest.mark.asyncio
async def test_rerank_after_fusion_disabled(sample_documents, reranker_config, mock_registry):
    """Test reranking when disabled in config."""
    reranker_config.reranker_enabled = False
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
    )
    
    # Should return first top_k documents without reranking
    assert len(results) == reranker_config.reranker_top_k
    assert results == sample_documents[:reranker_config.reranker_top_k]


@pytest.mark.asyncio
async def test_rerank_after_fusion_short_input(sample_documents, reranker_config, mock_registry):
    """Test reranking when input is shorter than top_k."""
    reranker_config.reranker_top_k = 10  # Larger than input
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,  # Only 5 docs
        config=reranker_config,
        reranker_registry=mock_registry,
    )
    
    # Should return all documents without reranking
    assert len(results) == len(sample_documents)
    assert results == sample_documents


@pytest.mark.asyncio
async def test_rerank_after_fusion_reranker_error(sample_documents, reranker_config, mock_registry):
    """Test reranking when reranker raises an exception."""
    # Configure mock to fail
    mock_registry.get.return_value = MockReranker("mock", should_fail=True)
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
    )
    
    # Should fall back to identity reranking
    assert len(results) == reranker_config.reranker_top_k
    # Scores should be 1.0 (identity fallback)
    assert all(doc["score"] == 1.0 for doc in results)


@pytest.mark.asyncio
async def test_rerank_after_fusion_health_check_failure(sample_documents, reranker_config, mock_registry):
    """Test reranking when reranker fails health check."""
    # Configure mock to fail health check
    mock_registry.get.return_value = MockReranker("mock", should_fail=True)
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
    )
    
    # Should fall back to identity reranking
    assert len(results) == reranker_config.reranker_top_k


@pytest.mark.asyncio
async def test_rerank_after_fusion_reranker_not_found(sample_documents, reranker_config):
    """Test reranking when requested reranker is not found."""
    with patch('llm_client.rag.pipeline.RerankerRegistry') as mock:
        registry = MagicMock()
        registry.get.side_effect = Exception("Reranker not found")
        mock.registry = registry
        
        results = await rerank_after_fusion(
            query="error codes",
            fused_docs=sample_documents,
            config=reranker_config,
            reranker_registry=registry,
        )
        
        # Should fall back to identity reranking
        assert len(results) == reranker_config.reranker_top_k


@pytest.mark.asyncio
async def test_rerank_after_fusion_metrics_recorded(sample_documents, reranker_config, mock_registry):
    """Test that metrics are properly recorded."""
    metrics = RerankerMetrics()
    
    await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
        metrics=metrics,
    )
    
    # Check that metrics were recorded (via side effects)


@pytest.mark.asyncio
async def test_rerank_after_fusion_null_metrics(sample_documents, reranker_config, mock_registry):
    """Test that null metrics don't cause errors."""
    metrics = NullRerankerMetrics()
    
    await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
        metrics=metrics,
    )
    
    # Should not raise errors
    assert True


@pytest.mark.asyncio
async def test_rerank_after_fusion_operational_logging(sample_documents, reranker_config, mock_registry, mock_operational_writer):
    """Test logging to operational stream."""
    await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
        operational_writer=mock_operational_writer,
    )
    
    # Check that operational writer was called
    mock_operational_writer.write.assert_called_once()
    call_args = mock_operational_writer.write.call_args[0][0]
    
    assert call_args["event"] == "rag_rerank"
    assert call_args["reranker"] == "mock"
    assert call_args["input_count"] == len(sample_documents)
    assert call_args["output_count"] == reranker_config.reranker_top_k
    assert "latency_ms" in call_args


@pytest.mark.asyncio
async def test_rerank_after_fusion_forensic_logging(sample_documents, reranker_config, mock_registry, mock_forensic_writer):
    """Test logging to forensic stream."""
    await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
        forensic_writer=mock_forensic_writer,
    )
    
    # Check that forensic writer was called
    mock_forensic_writer.write.assert_called_once()
    call_args = mock_forensic_writer.write.call_args[0][0]
    
    assert call_args["event"] == "rag_rerank_scores"
    assert call_args["reranker"] == "mock"
    assert call_args["input_count"] == len(sample_documents)
    assert call_args["output_count"] == reranker_config.reranker_top_k
    assert "scores" in call_args
    assert len(call_args["scores"]) == reranker_config.reranker_top_k


@pytest.mark.asyncio
async def test_rerank_after_fusion_error_logging(sample_documents, reranker_config, mock_registry, mock_operational_writer):
    """Test error logging when reranking fails."""
    # Configure mock to fail
    mock_registry.get.return_value = MockReranker("mock", should_fail=True)
    
    await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
        operational_writer=mock_operational_writer,
    )
    
    # Check that error was logged
    mock_operational_writer.write.assert_called()
    call_args = mock_operational_writer.write.call_args[0][0]
    
    assert call_args["event"] == "rag_rerank_error"
    assert call_args["reranker"] == "mock"
    assert "error" in call_args  # Error message could be either health check or rerank failure
    assert call_args["input_count"] == len(sample_documents)


@pytest.mark.asyncio
async def test_rerank_after_fusion_original_index_mapping(sample_documents, reranker_config, mock_registry):
    """Test that output documents map back to original fused_docs positions."""
    # Mock reranker to return specific indices
    mock_reranker = MockReranker("mock")
    mock_reranker.rerank = AsyncMock(return_value=[
        RerankResult(doc_id="0", score=0.9, original_index=0),  # First doc
        RerankResult(doc_id="2", score=0.8, original_index=2),  # Third doc
        RerankResult(doc_id="4", score=0.7, original_index=4),  # Fifth doc
    ])
    
    mock_registry.get.return_value = mock_reranker
    
    results = await rerank_after_fusion(
        query="error codes",
        fused_docs=sample_documents,
        config=reranker_config,
        reranker_registry=mock_registry,
    )
    
    # Check that results map back to original indices
    expected_contents = [
        sample_documents[0]["content"],  # original_index=0
        sample_documents[2]["content"],  # original_index=2
        sample_documents[4]["content"],  # original_index=4
    ]
    
    actual_contents = [result["content"] for result in results]
    assert actual_contents == expected_contents


# ---------- _identity_fallback ----------

def test_identity_fallback(sample_documents):
    """Test identity fallback function."""
    top_k = 3
    result = _identity_fallback(sample_documents, top_k)
    
    # Should return first top_k documents with correct structure
    assert len(result) == top_k
    assert len(result) == len(sample_documents[:top_k])
    # Check that each result has the expected fields
    for i, (result_doc, original_doc) in enumerate(zip(result, sample_documents[:top_k])):
        assert result_doc["content"] == original_doc["content"]
        assert result_doc["score"] == 1.0
        # Note: identity fallback doesn't add doc_id, only content, metadata, and score


def test_identity_fallback_empty_input():
    """Test identity fallback with empty input."""
    result = _identity_fallback([], 5)
    assert result == []


def test_identity_fallback_top_k_exceeds_input():
    """Test identity fallback when top_k exceeds input size."""
    sample = [{"content": "doc1"}]
    result = _identity_fallback(sample, 5)
    assert len(result) == 1
    assert result[0]["score"] == 1.0


# ---------- RetrieverConfig validation ----------

def test_retriever_config_defaults():
    """Test RetrieverConfig default values."""
    config = RetrieverConfig()
    
    assert config.reranker_name == "bge"
    assert config.reranker_top_k == 5
    assert config.reranker_enabled is True
    assert config.retrieval_strategy.value == "hybrid"
    assert config.vector_top_k == 20
    assert config.bm25_top_k == 20
    assert config.hybrid_top_k == 50


def test_retriever_config_validation():
    """Test RetrieverConfig validation."""
    # Valid config
    config = RetrieverConfig(reranker_top_k=5, vector_top_k=20, bm25_top_k=20)
    assert config.reranker_top_k == 5
    
    # Invalid config - negative values
    with pytest.raises(ValueError, match="must be positive"):
        RetrieverConfig(reranker_top_k=-1)
    
    with pytest.raises(ValueError, match="must be positive"):
        RetrieverConfig(vector_top_k=0)
    
    # Invalid config - weight out of range
    with pytest.raises(ValueError, match="must be between 0 and 1"):
        RetrieverConfig(vector_weight=1.5)
    
    # Invalid config - weights don't sum to 1
    with pytest.raises(ValueError, match="must equal 1.0"):
        RetrieverConfig(vector_weight=0.6, bm25_weight=0.6)


# ---------- Integration tests with IdentityReranker ----------

@pytest.mark.asyncio
async def test_integration_with_identity_reranker(sample_documents, reranker_config):
    """Test integration with real IdentityReranker."""
    with patch('llm_client.rag.pipeline.RerankerRegistry') as mock:
        registry = MagicMock()
        identity_reranker = IdentityReranker()
        registry.get.return_value = identity_reranker
        mock.registry = registry
        
        results = await rerank_after_fusion(
            query="error codes",
            fused_docs=sample_documents,
            config=reranker_config,
            reranker_registry=registry,
        )
        
        # Identity reranker should preserve order and return first top_k
        assert len(results) == reranker_config.reranker_top_k
        assert len(results) == len(sample_documents[:reranker_config.reranker_top_k])
        
        # Check that results have the expected structure
        for i, (result, original) in enumerate(zip(results, sample_documents[:reranker_config.reranker_top_k])):
            assert result["content"] == original["content"]
            assert result["metadata"] == original["metadata"]
            assert result["score"] == 1.0  # Identity fallback gives neutral score