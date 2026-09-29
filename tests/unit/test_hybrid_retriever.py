"""Unit tests for HybridRetriever."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_client.rag.config import RetrieverConfig
from llm_client.rag.metrics import NullRerankerMetrics
from llm_client.rag.retrieval.hybrid_retriever import HybridRetriever, RetrievalError


class MockVectorRetriever:
    """Mock LangChain VectorStoreRetriever for testing."""
    
    def __init__(self, documents=None, fail=False):
        self.documents = documents or []
        self.fail = fail
        self.aget_relevant_documents = AsyncMock()
        
        if fail:
            self.aget_relevant_documents.side_effect = Exception("Vector retrieval failed")
        else:
            self.aget_relevant_documents.return_value = self.documents


class MockBM25Retriever:
    """Mock BM25Retriever for testing."""
    
    def __init__(self, documents=None, fail=False):
        self.documents = documents or []
        self.fail = fail
        self.retrieve = AsyncMock()
        
        if fail:
            self.retrieve.side_effect = Exception("BM25 retrieval failed")
        else:
            self.retrieve.return_value = self.documents


class TestHybridRetriever:
    """Unit tests for HybridRetriever class."""
    
    @pytest.fixture
    def sample_vector_docs(self):
        """Create sample vector documents (LangChain Document format)."""
        from langchain_core.documents import Document
        
        return [
            Document(
                page_content="This is the first document content.",
                metadata={"title": "Vector Doc 1", "source": "vector"},
                id="vector_doc_1"
            ),
            Document(
                page_content="Second document for vector search.",
                metadata={"title": "Vector Doc 2", "source": "vector"},
                id="vector_doc_2"
            ),
            Document(
                page_content="Third document content here.",
                metadata={"title": "Vector Doc 3", "source": "vector"},
                score=0.8
            )
        ]
    
    @pytest.fixture
    def sample_bm25_docs(self):
        """Create sample BM25 documents (dict format)."""
        return [
            {
                "id": "bm25_doc_1",
                "content": "This is the first BM25 document content.",
                "metadata": {"title": "BM25 Doc 1", "source": "bm25"},
                "score": 0.9,
                "snippet": "<b>First</b> BM25 document content."
            },
            {
                "id": "bm25_doc_2",
                "content": "Second BM25 document with different content.",
                "metadata": {"title": "BM25 Doc 2", "source": "bm25"},
                "score": 0.7,
                "snippet": "Second BM25 document with <b>different</b> content."
            }
        ]
    
    @pytest.fixture
    def sample_config(self):
        """Create sample RetrieverConfig."""
        return RetrieverConfig(
            vector_top_k=20,
            bm25_top_k=20,
            hybrid_top_k=50
        )
    
    @pytest.fixture
    def mock_metrics(self):
        """Create mock metrics for testing."""
        return NullRerankerMetrics()
    
    @pytest.fixture
    def hybrid_retriever(self, sample_vector_docs, sample_bm25_docs, sample_config, mock_metrics):
        """Create a HybridRetriever instance for testing."""
        mock_vector = MockVectorRetriever(documents=sample_vector_docs)
        mock_bm25 = MockBM25Retriever(documents=sample_bm25_docs)
        
        return HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config,
            metrics=mock_metrics
        )
    
    @pytest.mark.asyncio
    async def test_happy_path(self, hybrid_retriever, sample_vector_docs, sample_bm25_docs):
        """Test successful hybrid retrieval with both retrievers working."""
        vector_docs, bm25_docs = await hybrid_retriever.aretrieve("test query", "user-123")
        
        # Verify both retrievers were called
        hybrid_retriever._vector.aget_relevant_documents.assert_called_once_with(
            "test query", k=20
        )
        hybrid_retriever._bm25.retrieve.assert_called_once_with(
            "test query", "user-123", 20
        )
        
        # Verify results
        assert len(vector_docs) == 3
        assert len(bm25_docs) == 2
        
        # Check vector docs are normalized
        assert vector_docs[0]["id"] == "vector_doc_1"
        assert vector_docs[0]["content"] == "This is the first document content."
        assert vector_docs[0]["metadata"]["title"] == "Vector Doc 1"
        assert "score" in vector_docs[0]
        
        # Check bm25 docs are unchanged format
        assert bm25_docs[0]["id"] == "bm25_doc_1"
        assert bm25_docs[0]["content"] == "This is the first BM25 document content."
        assert bm25_docs[0]["metadata"]["title"] == "BM25 Doc 1"
        assert bm25_docs[0]["score"] == 0.9
    
    @pytest.mark.asyncio
    async def test_vector_failure_bm25_success(self, sample_bm25_docs, sample_config):
        """Test hybrid retrieval when vector retriever fails but BM25 succeeds."""
        
        mock_metrics = MagicMock()
        mock_metrics.increment_error_count = MagicMock()
        
        mock_vector = MockVectorRetriever(fail=True)
        mock_bm25 = MockBM25Retriever(documents=sample_bm25_docs)
        
        retriever = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config,
            metrics=mock_metrics
        )
        
        vector_docs, bm25_docs = await retriever.aretrieve("test query", "user-123")
        
        # Verify vector docs is empty (failure handled)
        assert vector_docs == []
        
        # Verify bm25 docs are returned normally
        assert len(bm25_docs) == 2
        assert bm25_docs[0]["id"] == "bm25_doc_1"
        
        # Verify metrics were called
        mock_metrics.increment_error_count.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_bm25_failure_vector_success(self, sample_vector_docs, sample_config):
        """Test hybrid retrieval when BM25 retriever fails but vector succeeds."""
        
        mock_metrics = MagicMock()
        mock_metrics.increment_error_count = MagicMock()
        
        mock_vector = MockVectorRetriever(documents=sample_vector_docs)
        mock_bm25 = MockBM25Retriever(fail=True)
        
        retriever = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config,
            metrics=mock_metrics
        )
        
        vector_docs, bm25_docs = await retriever.aretrieve("test query", "user-123")
        
        # Verify bm25 docs is empty (failure handled)
        assert bm25_docs == []
        
        # Verify vector docs are returned normally
        assert len(vector_docs) == 3
        assert vector_docs[0]["id"] == "vector_doc_1"
        
        # Verify metrics were called
        mock_metrics.increment_error_count.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_complete_failure(self, sample_config):
        """Test hybrid retrieval when both retrievers fail."""
        
        mock_metrics = MagicMock()
        mock_metrics.increment_error_count = MagicMock()
        
        mock_vector = MockVectorRetriever(fail=True)
        mock_bm25 = MockBM25Retriever(fail=True)
        
        retriever = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config,
            metrics=mock_metrics
        )
        
        # Should raise RetrievalError
        with pytest.raises(RetrievalError, match="Hybrid retrieval failed"):
            await retriever.aretrieve("test query", "user-123")
        
        # Verify metrics were called twice (once for each failure)
        assert mock_metrics.increment_error_count.call_count == 2
    
    @pytest.mark.asyncio
    async def test_empty_query(self, hybrid_retriever):
        """Test hybrid retrieval with empty query."""
        vector_docs, bm25_docs = await hybrid_retriever.aretrieve("", "user-123")
        
        # Should return empty lists without calling retrievers
        assert vector_docs == []
        assert bm25_docs == []
        
        # Verify retrievers were not called
        hybrid_retriever._vector.aget_relevant_documents.assert_not_called()
        hybrid_retriever._bm25.retrieve.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_custom_top_k(self, sample_vector_docs, sample_bm25_docs, sample_config):
        """Test hybrid retrieval with custom top_k parameter."""
        mock_vector = MockVectorRetriever(documents=sample_vector_docs)
        mock_bm25 = MockBM25Retriever(documents=sample_bm25_docs)
        
        retriever = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config
        )
        
        # Use custom top_k_per_strategy
        vector_docs, bm25_docs = await retriever.aretrieve("test query", "user-123", top_k_per_strategy=10)
        
        # Verify both retrievers were called with custom top_k
        mock_vector.aget_relevant_documents.assert_called_once_with("test query", k=10)
        mock_bm25.retrieve.assert_called_once_with("test query", "user-123", 10)
        
        # Results should be limited to top_k
        assert len(vector_docs) <= 10
        assert len(bm25_docs) <= 10
    
    @pytest.mark.asyncio
    async def test_latency_metrics(self, sample_vector_docs, sample_bm25_docs, sample_config):
        """Test that latency is properly recorded."""
        
        mock_metrics = MagicMock()
        mock_metrics.increment_error_count = MagicMock()
        mock_metrics.record_latency = MagicMock()
        
        mock_vector = MockVectorRetriever(documents=sample_vector_docs)
        mock_bm25 = MockBM25Retriever(documents=sample_bm25_docs)
        
        retriever = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config,
            metrics=mock_metrics
        )
        
        await retriever.aretrieve("test query", "user-123")
        
        # Verify latency was recorded
        mock_metrics.record_latency.assert_called_once()
        latency_value = mock_metrics.record_latency.call_args[0][0]
        assert isinstance(latency_value, (int, float))
        assert latency_value >= 0
    
    @pytest.mark.asyncio
    async def test_vector_doc_normalization(self, sample_config):
        """Test that vector documents are properly normalized to common format."""
        # Create vector docs without id (should generate synthetic id)
        from langchain_core.documents import Document
        
        # Create documents - LangChain Documents don't support arbitrary attributes
        # so all will get synthetic scores
        vector_docs = [
            Document(
                page_content="Content without id",
                metadata={"title": "No ID Doc"}
            ),
            Document(
                page_content="Second document content",
                metadata={"title": "Second Doc"}
            ),
            Document(
                page_content="Third document here",
                metadata={"title": "Third Doc"}
            )
        ]
        
        mock_vector = MockVectorRetriever(documents=vector_docs)
        mock_bm25 = MockBM25Retriever(documents=[])
        
        retriever = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config
        )
        
        result_vector_docs, _ = await retriever.aretrieve("test query", "user-123")
        
        # Check normalization
        assert len(result_vector_docs) == 3
        
        # Check first document (synthetic id and score)
        assert result_vector_docs[0]["id"].startswith("vector_0_")  # Synthetic id with hash
        assert result_vector_docs[0]["content"] == "Content without id"
        assert result_vector_docs[0]["metadata"]["title"] == "No ID Doc"
        assert result_vector_docs[0]["score"] == 1.0 / 1  # Synthetic score (1.0)
        
        # Check second document (synthetic id and score)
        assert result_vector_docs[1]["id"].startswith("vector_1_")  # Synthetic id with hash
        assert result_vector_docs[1]["content"] == "Second document content"
        assert result_vector_docs[1]["metadata"]["title"] == "Second Doc"
        assert result_vector_docs[1]["score"] == 1.0 / 2  # Synthetic score (0.5)
        
        # Check third document (synthetic id and score)
        assert result_vector_docs[2]["id"].startswith("vector_2_")  # Synthetic id with hash
        assert result_vector_docs[2]["content"] == "Third document here"
        assert result_vector_docs[2]["metadata"]["title"] == "Third Doc"
        assert result_vector_docs[2]["score"] == 1.0 / 3  # Synthetic score (~0.333)
    
    def test_retrieval_error(self):
        """Test RetrievalError exception."""
        error = RetrievalError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)
    
    def test_initialization(self, sample_vector_docs, sample_bm25_docs, sample_config):
        """Test HybridRetriever initialization."""
        mock_vector = MockVectorRetriever(documents=sample_vector_docs)
        mock_bm25 = MockBM25Retriever(documents=sample_bm25_docs)
        
        # Test with metrics
        metrics = NullRerankerMetrics()
        retriever = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config,
            metrics=metrics
        )
        
        assert retriever._vector == mock_vector
        assert retriever._bm25 == mock_bm25
        assert retriever._config == sample_config
        assert retriever._metrics == metrics
        
        # Test without metrics (should use default)
        retriever_no_metrics = HybridRetriever(
            vector_retriever=mock_vector,
            bm25_retriever=mock_bm25,
            config=sample_config
        )
        assert retriever_no_metrics._metrics is not None