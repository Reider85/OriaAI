"""Unit tests for BM25Retriever."""


import pytest

from llm_client.rag.retrieval.bm25_retriever import BM25Retriever


class MockAsyncConnection:
    """Mock asyncpg connection for testing."""
    
    def __init__(self):
        self.execute_calls = []
        self.fetch_calls = []
        self.fetch_results = []
    
    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))
        return "SET"
    
    async def fetch(self, sql, *args):
        self.fetch_calls.append((sql, args))
        return self.fetch_results
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockAsyncPool:
    """Mock asyncpg pool for testing."""
    
    def __init__(self):
        self.connection = MockAsyncConnection()
        self.acquire_calls = []
    
    def acquire(self):
        self.acquire_calls.append(True)
        return self.connection
    
    def release(self, conn):
        pass


class TestBM25Retriever:
    """Unit tests for BM25Retriever class."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock asyncpg pool."""
        return MockAsyncPool()
    
    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        return [
            {
                "id": "doc-123",
                "content": "This is the first document content for testing.",
                "metadata": {"title": "Test Document 1"},
                "bm25_score": 0.8,
                "snippet": "<b>This</b> is the first document content for testing."
            },
            {
                "id": "doc-456", 
                "content": "Second document with different content.",
                "metadata": {"title": "Test Document 2"},
                "bm25_score": 0.6,
                "snippet": "Second document with <b>different</b> content."
            }
        ]
    
    @pytest.fixture
    def mock_retriever(self, mock_pool):
        """Create a BM25Retriever instance for testing."""
        return BM25Retriever(mock_pool, text_search_config="english", fuzzy_enabled=False)
    
    @pytest.mark.asyncio
    async def test_retrieve_basic(self, mock_retriever, mock_pool, sample_documents):
        """Test basic document retrieval."""
        # Set up mock results
        mock_pool.connection.fetch_results = sample_documents
        
        # Execute retrieval
        results = await mock_retriever.retrieve("test query", "user-123", top_k=10)
        
        # Verify SQL call
        assert len(mock_pool.connection.fetch_calls) == 1
        sql_call = mock_pool.connection.fetch_calls[0]
        sql, args = sql_call
        
        # Check that SQL contains expected components
        assert "ts_rank(search_vector, query) AS bm25_score" in sql
        assert "ts_headline('english', content, query" in sql
        assert "WHERE search_vector @@ query" in sql
        assert "AND user_id = $2" in sql
        assert "ORDER BY bm25_score DESC" in sql
        assert "LIMIT $3" in sql
        
        # Check parameters
        assert args == ("test query", "user-123", 10)
        
        # Verify results
        assert len(results) == 2
        assert results[0]["id"] == "doc-123"
        assert results[0]["content"] == "This is the first document content for testing."
        assert results[0]["metadata"] == {"title": "Test Document 1"}
        assert results[0]["score"] == 0.8
        assert "<b>This</b>" in results[0]["snippet"]
    
    @pytest.mark.asyncio
    async def test_retrieve_with_fuzzy(self, mock_pool, sample_documents):
        """Test retrieval with fuzzy matching enabled."""
        retriever = BM25Retriever(mock_pool, text_search_config="english", fuzzy_enabled=True)
        mock_pool.connection.fetch_results = sample_documents
        
        await retriever.retrieve("test query", "user-123", top_k=10)
        
        # Verify fuzzy SQL is used
        sql_call = mock_pool.connection.fetch_calls[0]
        sql, args = sql_call
        assert "similarity($1, d.content) AS fuzzy_score" in sql
        assert "OR d.content % $1" in sql
        assert "(bm25_score + fuzzy_score * 0.3)" in sql
    
    @pytest.mark.asyncio
    async def test_retrieve_empty_query(self, mock_retriever, mock_pool):
        """Test retrieval with empty query."""
        results = await mock_retriever.retrieve("", "user-123", top_k=10)
        
        # Should return empty list without calling database
        assert results == []
        assert len(mock_pool.connection.fetch_calls) == 0
    
    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self, mock_retriever, mock_pool):
        """Test retrieval with no results."""
        mock_pool.connection.fetch_results = []
        
        results = await mock_retriever.retrieve("test query", "user-123", top_k=10)
        
        # Should return empty list
        assert results == []
        assert len(mock_pool.connection.fetch_calls) == 1
    
    @pytest.mark.asyncio
    async def test_retrieve_text_search_config(self, mock_retriever, mock_pool, sample_documents):
        """Test retrieval with custom text search config."""
        mock_pool.connection.fetch_results = sample_documents
        
        # Create retriever with russian config
        retriever = BM25Retriever(mock_pool, text_search_config="russian", fuzzy_enabled=False)
        await retriever.retrieve("test query", "user-123", top_k=10)
        
        # Verify SET command was called with russian config
        set_calls = [
            call for call in mock_pool.connection.execute_calls if call[0].startswith("SET")
        ]
        assert len(set_calls) == 1
        sql, config = set_calls[0]
        assert sql == "SET search_config = 'russian'"
        assert config == ()
    
    @pytest.mark.asyncio
    async def test_retrieve_connection_error(self, mock_retriever, mock_pool):
        """Test handling of connection errors."""
        # Mock connection to raise an exception
        class ConnectionError(Exception):
            pass
        
        async def failing_execute(*args, **kwargs):
            raise ConnectionError("Connection failed")
        mock_pool.connection.execute = failing_execute
        
        # Should raise the exception
        with pytest.raises(ConnectionError, match="Connection failed"):
            await mock_retriever.retrieve("test query", "user-123", top_k=10)
    
    @pytest.mark.asyncio 
    async def test_retrieve_database_error(self, mock_retriever, mock_pool):
        """Test handling of database errors."""
        # Mock fetch to raise an exception
        class DatabaseError(Exception):
            pass
        
        async def failing_fetch(*args, **kwargs):
            raise DatabaseError("Database error")
        mock_pool.connection.fetch = failing_fetch
        
        # Should raise the exception
        with pytest.raises(DatabaseError, match="Database error"):
            await mock_retriever.retrieve("test query", "user-123", top_k=10)
    
    @pytest.mark.asyncio
    async def test_retrieve_single_result(self, mock_retriever, mock_pool):
        """Test retrieval with single result."""
        single_doc = [
            {
                "id": "doc-123",
                "content": "Single document result",
                "metadata": {"title": "Single Doc"},
                "bm25_score": 1.0,
                "snippet": "<b>Single</b> document result",
            }
        ]
        mock_pool.connection.fetch_results = single_doc
        
        results = await mock_retriever.retrieve("test query", "user-123", top_k=1)
        
        assert len(results) == 1
        assert results[0]["id"] == "doc-123"
        assert results[0]["score"] == 1.0
    
    @pytest.mark.asyncio
    async def test_retrieve_top_k_limit(self, mock_retriever, mock_pool, sample_documents):
        """Test that top_k parameter is properly used in SQL."""
        mock_pool.connection.fetch_results = sample_documents
        
        # Request only 1 document
        await mock_retriever.retrieve("test query", "user-123", top_k=1)
        
        # Verify LIMIT parameter
        sql_call = mock_pool.connection.fetch_calls[0]
        sql, args = sql_call
        assert args == ("test query", "user-123", 1)
    
    def test_retriever_initialization(self):
        """Test BM25Retriever initialization."""
        mock_pool = MockAsyncPool()
        
        # Test with default values
        retriever = BM25Retriever(mock_pool)
        assert retriever._pool == mock_pool
        assert retriever._text_search_config == "english"
        assert retriever._fuzzy_enabled == False
        
        # Test with custom values
        retriever = BM25Retriever(mock_pool, text_search_config="russian", fuzzy_enabled=True)
        assert retriever._text_search_config == "russian"
        assert retriever._fuzzy_enabled == True