"""Unit tests for CohereRerankAdapter."""

import pytest
from unittest.mock import AsyncMock

from llm_client.rag.rerankers.base import RerankResult
from llm_client.rag.rerankers.cohere import CohereRerankAdapter


class MockCohereResponse:
    """Mock Cohere rerank response for testing."""
    
    def __init__(self, results):
        self.results = results


class MockCohereClient:
    """Mock Cohere AsyncClient for testing."""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.models = AsyncMock()
        self.models.list = AsyncMock(return_value={"models": []})
        self.rerank = self._rerank
    
    async def _rerank(
        self,
        model: str,
        query: str,
        documents: list,
        top_n: int = 5,
        return_documents: bool = False,
    ):
        """Return mock rerank results with deterministic scores."""
        # Return scores: first document always highest, then descending
        scores = [0.9, 0.1, 0.7, 0.3, 0.8][:len(documents)]
        # Sort by score descending and return top_n results
        indexed = [(i, float(s)) for i, s in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        top_results = indexed[:top_n]
        
        results = [
            type('MockResult', (), {
                'index': i,
                'relevance_score': s
            })() for i, s in top_results
        ]
        return MockCohereResponse(results)


@pytest.fixture
def cohere_reranker():
    """CohereRerankAdapter with pre-loaded mock client."""
    adapter = CohereRerankAdapter(api_key="test-key")
    adapter._client = MockCohereClient("test-key")
    return adapter


@pytest.fixture
def sample_documents():
    """5 sample documents for testing."""
    return [
        {"id": "doc1", "content": "This is about error codes and debugging"},
        {"id": "doc2", "content": "Unrelated document about cooking recipes"},
        {"id": "doc3", "content": "Another document about error handling"},
        {"id": "doc4", "content": "Document about system architecture"},
        {"id": "doc5", "content": "Final document about error recovery"},
    ]


@pytest.mark.asyncio
async def test_rerank_basic_functionality(cohere_reranker, sample_documents):
    """Test basic rerank functionality."""
    results = await cohere_reranker.rerank("query", sample_documents, top_k=3)
    assert len(results) == 3
    assert all(isinstance(r, RerankResult) for r in results)
    # Results should be sorted by score (highest first)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_rerank_empty_documents(cohere_reranker):
    """Test rerank with empty documents."""
    results = await cohere_reranker.rerank("query", [], top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_name_property(cohere_reranker):
    """Test name property."""
    assert cohere_reranker.name == "cohere-rerank"


@pytest.mark.asyncio
async def test_lazy_loading_not_loaded_in_init():
    """Test that the client is lazy-loaded."""
    adapter = CohereRerankAdapter(api_key="test-key")
    assert adapter._client is None


@pytest.mark.asyncio
async def test_health_check_success(cohere_reranker):
    """Test health check success."""
    assert await cohere_reranker.health_check() is True


@pytest.mark.asyncio
async def test_entry_point_registration():
    """Test that CohereRerankAdapter can be loaded via entry point."""
    from llm_client.rag.rerankers.registry import get_reranker
    
    # This should work without raising an exception
    reranker = get_reranker("cohere")
    assert reranker.name == "cohere-rerank"