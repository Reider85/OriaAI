"""Unit tests for BM25IndexBuilder, Chunk, and index_chunks."""

import json

import pytest

from llm_client.rag.indexing.bm25_indexer import BM25IndexBuilder
from llm_client.rag.indexing.models import Chunk, Document


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
        return MockAsyncPool()

    @pytest.fixture
    def sample_document(self):
        return Document(
            id="doc-123",
            user_id="user-456",
            source_type="file",
            source_uri="/path/to/doc.txt",
            content_hash="abc123",
            content="This is the document content for testing.",
            metadata={"title": "Test Document", "author": "Test Author"},
        )

    @pytest.mark.asyncio
    async def test_index_document_insert(self, mock_pool, sample_document):
        """INSERT must not supply search_vector (generated column) and must not SET config."""
        indexer = BM25IndexBuilder(mock_pool)

        await indexer.index_document(sample_document)

        assert len(mock_pool.connection.execute_calls) == 1
        sql, args = mock_pool.connection.execute_calls[0]

        assert "INSERT INTO documents" in sql
        assert "search_vector" not in sql
        assert "SET pg_text_search_config" not in sql
        assert "VALUES ($1, $2, $3, $4, $5, $6, $7)" in sql
        assert "ON CONFLICT (content_hash) DO UPDATE SET" in sql
        assert "content = EXCLUDED.content" in sql
        assert "metadata = EXCLUDED.metadata" in sql
        assert "source_uri = EXCLUDED.source_uri" in sql

        assert args == (
            "doc-123",
            "user-456",
            "file",
            "/path/to/doc.txt",
            "abc123",
            "This is the document content for testing.",
            json.dumps({"title": "Test Document", "author": "Test Author"}),
        )

    @pytest.mark.asyncio
    async def test_index_document_upsert(self, mock_pool):
        indexer = BM25IndexBuilder(mock_pool)

        doc = Document(
            id="doc-456",
            user_id="user-789",
            source_type="file",
            source_uri="/path/to/updated.txt",
            content_hash="abc123",
            content="Updated document content.",
            metadata={"title": "Updated Document"},
        )

        await indexer.index_document(doc)

        assert len(mock_pool.connection.execute_calls) == 1
        sql, _args = mock_pool.connection.execute_calls[0]
        assert "ON CONFLICT (content_hash) DO UPDATE" in sql
        assert "content = EXCLUDED.content" in sql

    @pytest.mark.asyncio
    async def test_index_documents_batch(self, mock_pool):
        indexer = BM25IndexBuilder(mock_pool)

        documents = [
            Document(
                id="doc-1",
                user_id="user-1",
                source_type="file",
                content_hash="hash1",
                content="Content 1",
            ),
            Document(
                id="doc-2",
                user_id="user-2",
                source_type="file",
                content_hash="hash2",
                content="Content 2",
            ),
            Document(
                id="doc-3",
                user_id="user-3",
                source_type="file",
                content_hash="hash3",
                content="Content 3",
            ),
        ]

        await indexer.index_documents_batch(documents)

        assert len(mock_pool.connection.executemany_calls) == 1
        sql, data = mock_pool.connection.executemany_calls[0]
        assert "INSERT INTO documents" in sql
        assert "search_vector" not in sql
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_index_documents_batch_empty(self, mock_pool):
        indexer = BM25IndexBuilder(mock_pool)
        await indexer.index_documents_batch([])
        assert len(mock_pool.connection.executemany_calls) == 0

    @pytest.mark.asyncio
    async def test_index_chunks_concatenates_content(self, mock_pool):
        """Chunks of the same document are joined by chunk_index order."""
        indexer = BM25IndexBuilder(mock_pool)

        chunks = [
            Chunk(
                document_id="doc-1",
                user_id="user-1",
                source_type="file",
                content="second part",
                chunk_index=1,
                content_hash="hash-doc-1",
                metadata={"title": "Doc 1"},
            ),
            Chunk(
                document_id="doc-1",
                user_id="user-1",
                source_type="file",
                content="first part",
                chunk_index=0,
                content_hash="hash-doc-1",
                metadata={"title": "Doc 1"},
            ),
        ]

        await indexer.index_chunks(chunks)

        assert len(mock_pool.connection.executemany_calls) == 1
        sql, data = mock_pool.connection.executemany_calls[0]
        assert "INSERT INTO documents" in sql
        assert len(data) == 1
        row = data[0]
        assert row[0] == "doc-1"
        assert row[5] == "first part\nsecond part"
        assert row[4] == "hash-doc-1"

    @pytest.mark.asyncio
    async def test_index_chunks_multiple_documents(self, mock_pool):
        indexer = BM25IndexBuilder(mock_pool)

        chunks = [
            Chunk(
                document_id="doc-a", user_id="u", source_type="file", content="a0", chunk_index=0
            ),
            Chunk(
                document_id="doc-b", user_id="u", source_type="file", content="b0", chunk_index=0
            ),
            Chunk(
                document_id="doc-a", user_id="u", source_type="file", content="a1", chunk_index=1
            ),
        ]

        await indexer.index_chunks(chunks)

        _sql, data = mock_pool.connection.executemany_calls[0]
        assert len(data) == 2
        contents = {row[0]: row[5] for row in data}
        assert contents["doc-a"] == "a0\na1"
        assert contents["doc-b"] == "b0"

    @pytest.mark.asyncio
    async def test_delete_document(self, mock_pool):
        indexer = BM25IndexBuilder(mock_pool)
        await indexer.delete_document("doc-123")
        sql, args = mock_pool.connection.execute_calls[0]
        assert sql == "DELETE FROM documents WHERE id = $1"
        assert args == ("doc-123",)

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, mock_pool):
        class _Boom(Exception):
            pass

        async def failing_execute(*args, **kwargs):
            raise _Boom("Connection failed")

        mock_pool.connection.execute = failing_execute
        indexer = BM25IndexBuilder(mock_pool)
        document = Document(
            id="doc-123",
            user_id="user-123",
            source_type="file",
            content_hash="hash",
            content="test",
        )

        with pytest.raises(_Boom, match="Connection failed"):
            await indexer.index_document(document)

    def test_document_model(self):
        doc = Document(
            id="test-id",
            user_id="test-user",
            source_type="file",
            content_hash="test-hash",
            content="test content",
        )
        assert doc.id == "test-id"
        assert doc.metadata == {}

    def test_document_auto_content_hash(self):
        doc = Document(
            id="test-id",
            user_id="test-user",
            source_type="file",
            content="hello world",
        )
        assert len(doc.content_hash) == 64

    def test_chunk_model(self):
        chunk = Chunk(
            document_id="d1",
            user_id="u1",
            source_type="file",
            content="chunk text",
        )
        assert chunk.chunk_index == 0
        assert chunk.metadata == {}
