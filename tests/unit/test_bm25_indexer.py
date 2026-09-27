"""Unit tests for BM25IndexBuilder."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llm_client.rag.indexing.bm25_indexer import BM25IndexBuilder
from llm_client.rag.indexing.models import Document


class MockAsyncConnection:
    """Mock asyncpg connection for testing."""
    
    def __init__(self):
        self.execute_calls = []
        self.executemany_calls = []
    
    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))
        return "INSERT 0 1"
    
    async def executemany(self, sql, args):
        self.executemany_calls.append((sql, args))
        return "INSERT 0 1"
    
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


class TestBM25IndexBuilder:
    """Unit tests for BM25IndexBuilder class."""
    
    @pytest.fixture
    def mock_pool(self):
        """Create a mock asyncpg pool."""
        return MockAsyncPool()
    
    @pytest.fixture
    def sample_document(self):
        """Create a sample document for testing."""
        return Document(
            id="doc-123",
            user_id="user-456",
            source_type="file",
            source_uri="/path/to/doc.txt",
            content_hash="abc123",
            content="This is the document content for testing.",
            metadata={"title": "Test Document", "author": "Test Author"}
        )
    
    @pytest.mark.asyncio
    async def test_index_document_insert(self, mock_pool, sample_document):
        """Test inserting a new document."""
        indexer = BM25IndexBuilder(mock_pool)
        
        await indexer.index_document(sample_document)
        
        # Verify the SQL call
        assert len(mock_pool.connection.execute_calls) == 1
        sql, args = mock_pool.connection.execute_calls[0]
        
        # Check that SQL contains the expected components
        assert "INSERT INTO documents" in sql
        assert "VALUES ($1, $2, $3, $4, $5, $6, $7)" in sql
        assert "ON CONFLICT (content_hash) DO UPDATE SET" in sql
        assert "content = EXCLUDED.content" in sql
        assert "metadata = EXCLUDED.metadata" in sql
        assert "source_uri = EXCLUDED.source_uri" in sql
        
        assert args == (
            "doc-123", "user-456", "file", "/path/to/doc.txt",
            "abc123", "This is the document content for testing.",
            {"title": "Test Document", "author": "Test Author"}
        )
    
    @pytest.mark.asyncio
    async def test_index_document_upsert(self, mock_pool):
        """Test updating an existing document (upsert behavior)."""
        indexer = BM25IndexBuilder(mock_pool)
        
        # Create document with same content_hash but different content
        doc = Document(
            id="doc-456",
            user_id="user-789",
            source_type="file",
            source_uri="/path/to/updated.txt",
            content_hash="abc123",  # Same hash as existing
            content="Updated document content.",
            metadata={"title": "Updated Document"}
        )
        
        await indexer.index_document(doc)
        
        # Verify the SQL call includes the update
        assert len(mock_pool.connection.execute_calls) == 1
        sql, args = mock_pool.connection.execute_calls[0]
        
        assert "ON CONFLICT (content_hash) DO UPDATE" in sql
        assert "content = EXCLUDED.content" in sql
    
    @pytest.mark.asyncio
    async def test_index_documents_batch(self, mock_pool):
        """Test batch indexing of multiple documents."""
        indexer = BM25IndexBuilder(mock_pool)
        
        documents = [
            Document(id="doc-1", user_id="user-1", source_type="file", content_hash="hash1", content="Content 1"),
            Document(id="doc-2", user_id="user-2", source_type="file", content_hash="hash2", content="Content 2"),
            Document(id="doc-3", user_id="user-3", source_type="file", content_hash="hash3", content="Content 3"),
        ]
        
        await indexer.index_documents_batch(documents)
        
        # Verify executemany was called
        assert len(mock_pool.connection.executemany_calls) == 1
        sql, data = mock_pool.connection.executemany_calls[0]
        
        assert "INSERT INTO documents" in sql
        assert len(data) == 3  # Three documents
    
    @pytest.mark.asyncio
    async def test_index_documents_batch_empty(self, mock_pool):
        """Test batch indexing with empty list."""
        indexer = BM25IndexBuilder(mock_pool)
        
        await indexer.index_documents_batch([])
        
        # Should not call the database
        assert len(mock_pool.connection.executemany_calls) == 0
    
    @pytest.mark.asyncio
    async def test_delete_document(self, mock_pool):
        """Test deleting a document."""
        indexer = BM25IndexBuilder(mock_pool)
        
        await indexer.delete_document("doc-123")
        
        # Verify the SQL call
        assert len(mock_pool.connection.execute_calls) == 1
        sql, args = mock_pool.connection.execute_calls[0]
        
        assert sql == "DELETE FROM documents WHERE id = $1"
        assert args == ("doc-123",)
    
    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, mock_pool):
        """Test deleting a non-existent document."""
        indexer = BM25IndexBuilder(mock_pool)
        
        await indexer.delete_document("nonexistent-doc")
        
        # Verify the SQL call was still made
        assert len(mock_pool.connection.execute_calls) == 1
        sql, args = mock_pool.connection.execute_calls[0]
        
        assert sql == "DELETE FROM documents WHERE id = $1"
        assert args == ("nonexistent-doc",)
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self, mock_pool):
        """Test handling of connection errors."""
        # Mock connection to raise an exception
        original_execute = mock_pool.connection.execute
        async def failing_execute(*args, **kwargs):
            raise Exception("Connection failed")
        mock_pool.connection.execute = failing_execute
        
        indexer = BM25IndexBuilder(mock_pool)
        document = Document(id="doc-123", user_id="user-123", source_type="file", content_hash="hash", content="test")
        
        # Should raise the exception
        with pytest.raises(Exception, match="Connection failed"):
            await indexer.index_document(document)
        
        # Restore original method
        mock_pool.connection.execute = original_execute
    
    def test_document_model(self):
        """Test Document dataclass validation."""
        doc = Document(
            id="test-id",
            user_id="test-user",
            source_type="file",
            content_hash="test-hash",
            content="test content"
        )
        
        assert doc.id == "test-id"
        assert doc.user_id == "test-user"
        assert doc.source_type == "file"
        assert doc.source_uri is None
        assert doc.content_hash == "test-hash"
        assert doc.content == "test content"
        assert doc.metadata == {}  # Should be initialized as empty dict
    
    def test_document_model_with_metadata(self):
        """Test Document dataclass with metadata."""
        metadata = {"title": "Test", "tags": ["tag1", "tag2"]}
        doc = Document(
            id="test-id",
            user_id="test-user",
            source_type="file",
            content_hash="test-hash",
            content="test content",
            metadata=metadata
        )
        
        assert doc.metadata == metadata
    
    def test_document_model_metadata_none_initialization(self):
        """Test that metadata is initialized as empty dict when None."""
        doc = Document(
            id="test-id",
            user_id="test-user",
            source_type="file",
            content_hash="test-hash",
            content="test content",
            metadata=None
        )
        
        assert doc.metadata == {}