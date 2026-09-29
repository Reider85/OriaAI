"""Integration test for HybridRetriever with real components."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.retrieval.hybrid_retriever import HybridRetriever


class MockVectorRetriever:
    """Mock LangChain VectorStoreRetriever for integration testing."""
    
    def __init__(self, documents):
        self.documents = documents
        self.aget_relevant_documents = AsyncMock()
        self.aget_relevant_documents.side_effect = self._mock_aget_relevant_documents
    
    async def _mock_aget_relevant_documents(self, query, k):
        """Mock async method to return vector documents."""
        # Simulate some latency
        await asyncio.sleep(0.01)
        
        # Return LangChain Document objects
        from langchain_core.documents import Document
        return [
            Document(
                page_content=doc["content"],
                metadata=doc["metadata"],
                id=doc.get("id", f"vector_{i}")
            )
            for i, doc in enumerate(self.documents[:k])
        ]


@pytest.mark.asyncio
async def test_hybrid_retriever_integration():
    """Test HybridRetriever with mock vector retriever and real BM25Retriever setup."""
    # Sample documents
    vector_docs = [
        {"id": "vec_doc_1", "content": "This is a vector document about AI and machine learning.", "metadata": {"source": "vector", "topic": "AI"}},
        {"id": "vec_doc_2", "content": "Vector search uses embeddings for semantic similarity.", "metadata": {"source": "vector", "topic": "search"}},
        {"id": "vec_doc_3", "content": "Machine learning algorithms can process large datasets.", "metadata": {"source": "vector", "topic": "ML"}},
    ]
    
    bm25_docs = [
        {"id": "bm25_doc_1", "content": "BM25 search uses keyword matching and term frequency.", "metadata": {"source": "bm25", "topic": "search"}},
        {"id": "bm25_doc_2", "content": "Full-text search algorithms like BM25 are efficient for exact matches.", "metadata": {"source": "bm25", "topic": "search"}},
    ]
    
    # Create mock vector retriever
    mock_vector = MockVectorRetriever(vector_docs)
    
    # Create mock BM25 retriever (since we don't have a real database for this test)
    mock_bm25 = MagicMock()
    mock_bm25.retrieve = AsyncMock(return_value=bm25_docs)
    
    # Create config
    config = RetrieverConfig(
        vector_top_k=3,
        bm25_top_k=3,
        hybrid_top_k=5
    )
    
    # Create HybridRetriever
    hybrid_retriever = HybridRetriever(
        vector_retriever=mock_vector,
        bm25_retriever=mock_bm25,
        config=config
    )
    
    # Test retrieval
    vector_results, bm25_results = await hybrid_retriever.aretrieve("search query", "user_123")
    
    # Verify results
    assert len(vector_results) == 3
    assert len(bm25_results) == 2
    
    # Verify vector results are normalized
    assert vector_results[0]["id"] == "vec_doc_1"
    assert vector_results[0]["content"] == "This is a vector document about AI and machine learning."
    assert vector_results[0]["metadata"]["source"] == "vector"
    assert "score" in vector_results[0]
    
    # Verify BM25 results are unchanged
    assert bm25_results[0]["id"] == "bm25_doc_1"
    assert bm25_results[0]["content"] == "BM25 search uses keyword matching and term frequency."
    assert bm25_results[0]["metadata"]["source"] == "bm25"
    
    # Verify both retrievers were called
    mock_vector.aget_relevant_documents.assert_called_once_with("search query", k=3)
    mock_bm25.retrieve.assert_called_once_with("search query", "user_123", 3)


@pytest.mark.asyncio
async def test_hybrid_retriever_partial_failure():
    """Test HybridRetriever when vector retriever fails."""
    # Create failing vector retriever
    class FailingVectorRetriever:
        async def aget_relevant_documents(self, query, k):
            raise Exception("Vector service unavailable")
    
    # Working BM25 retriever
    mock_bm25 = AsyncMock()
    mock_bm25.retrieve = AsyncMock(return_value=[
        {"id": "bm25_doc_1", "content": "BM25 document", "metadata": {}, "score": 0.8}
    ])
    
    # Create config
    config = RetrieverConfig(
        vector_top_k=2,
        bm25_top_k=1,
        hybrid_top_k=3
    )
    
    # Create HybridRetriever
    hybrid_retriever = HybridRetriever(
        vector_retriever=FailingVectorRetriever(),
        bm25_retriever=mock_bm25,
        config=config
    )
    
    # Should not raise exception, should return empty vector results and BM25 results
    vector_results, bm25_results = await hybrid_retriever.aretrieve("test query", "user_123")
    
    assert vector_results == []
    assert len(bm25_results) == 1
    assert bm25_results[0]["id"] == "bm25_doc_1"


@pytest.mark.asyncio 
async def test_hybrid_retriever_custom_top_k():
    """Test HybridRetriever with custom top_k parameter."""
    vector_docs = [
        {"content": "Vector doc 1", "metadata": {}},
        {"content": "Vector doc 2", "metadata": {}},
    ]
    
    mock_vector = MockVectorRetriever(vector_docs)
    mock_bm25 = MagicMock()
    mock_bm25.retrieve = AsyncMock(return_value=[
        {"id": "bm25_doc_1", "content": "BM25 doc", "metadata": {}, "score": 0.9}
    ])
    
    config = RetrieverConfig(
        vector_top_k=10,
        bm25_top_k=10,
        hybrid_top_k=20
    )
    
    hybrid_retriever = HybridRetriever(
        vector_retriever=mock_vector,
        bm25_retriever=mock_bm25,
        config=config
    )
    
    # Use custom top_k
    vector_results, bm25_results = await hybrid_retriever.aretrieve(
        "test query", "user_123", top_k_per_strategy=5
    )
    
    # Verify both retrievers were called with custom top_k
    mock_vector.aget_relevant_documents.assert_called_once_with("test query", k=5)
    mock_bm25.retrieve.assert_called_once_with("test query", "user_123", 5)
    
    # Results should be limited
    assert len(vector_results) <= 5
    assert len(bm25_results) <= 1