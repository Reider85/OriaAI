"""Integration tests for BM25Retriever with real PostgreSQL."""

import uuid

import asyncpg
import pytest

from llm_client.rag.indexing.bm25_indexer import BM25IndexBuilder
from llm_client.rag.indexing.models import Document
from llm_client.rag.retrieval.bm25_retriever import BM25Retriever


@pytest.mark.integration
class TestBM25RetrievalIntegration:
    """Integration tests for BM25Retriever with real PostgreSQL."""

    @pytest.fixture
    async def indexer(self, database_url):
        """Create BM25IndexBuilder with real PostgreSQL connection."""
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        indexer = BM25IndexBuilder(pool, text_search_config="english")
        yield indexer
        await pool.close()

    @pytest.fixture
    async def retriever(self, database_url):
        """Create BM25Retriever with real PostgreSQL connection."""
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        retriever = BM25Retriever(pool, text_search_config="english", fuzzy_enabled=False)
        yield retriever
        await pool.close()

    @pytest.fixture
    async def fuzzy_retriever(self, database_url):
        """Create BM25Retriever with fuzzy matching enabled."""
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        retriever = BM25Retriever(pool, text_search_config="english", fuzzy_enabled=True)
        yield retriever
        await pool.close()

    @pytest.fixture
    def test_documents(self):
        """Create test documents for integration tests."""
        return [
            Document(
                id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                source_type="test",
                content_hash=f"hash{i}",
                content="Error code 1234: This document contains important error information about system failures and troubleshooting steps for network connectivity issues.",
                metadata={"title": f"Error Document {i}", "category": "system"},
            )
            for i in range(5)
        ]

    @pytest.mark.asyncio
    async def test_retrieve_exact_match(self, indexer, retriever, test_documents):
        """Test retrieval with exact term match."""
        user_id = test_documents[0].user_id

        # Index all documents
        await indexer.index_documents_batch(test_documents)

        # Search for exact term
        results = await retriever.retrieve("error code 1234", user_id, top_k=3)

        # Should find documents containing the exact phrase
        assert len(results) >= 1

        # Verify results contain expected content
        found = any("Error code 1234" in result["content"] for result in results)
        assert found

        # Verify score and snippet are present
        for result in results:
            assert "score" in result
            assert "snippet" in result
            assert isinstance(result["score"], float)
            assert result["score"] > 0

    @pytest.mark.asyncio
    async def test_retrieve_with_snippet_highlighting(self, indexer, retriever, test_documents):
        """Test that snippets contain highlighted terms."""
        user_id = test_documents[0].user_id

        await indexer.index_documents_batch(test_documents)

        results = await retriever.retrieve("error code", user_id, top_k=3)

        # Check that snippets contain <b> highlighting
        for result in results:
            snippet = result["snippet"]
            assert "<b>" in snippet or "</b>" in snippet  # Should have highlighting
            assert (
                "error" in snippet.lower() or "code" in snippet.lower()
            )  # Should contain search terms

    @pytest.mark.asyncio
    async def test_retrieve_user_isolation(self, indexer, retriever, test_documents):
        """Test that users only see their own documents."""
        user1_id = test_documents[0].user_id
        user2_id = str(uuid.uuid4())

        # Index documents for user1
        await indexer.index_documents_batch(test_documents)

        # Create a document for user2
        user2_doc = Document(
            id=str(uuid.uuid4()),
            user_id=user2_id,
            source_type="test",
            content_hash="user2_hash",
            content="This belongs to user2 only",
            metadata={},
        )
        await indexer.index_document(user2_doc)

        # User1 should only see their own documents
        results_user1 = await retriever.retrieve("error", user1_id, top_k=10)
        assert len(results_user1) >= 1  # Should find user1's documents

        # User2 should only see their own document
        results_user2 = await retriever.retrieve("user2", user2_id, top_k=10)
        assert len(results_user2) == 1  # Should find only their own document
        assert "user2" in results_user2[0]["content"]

        # User2 should not see user1's documents when searching for "error"
        results_user2_error = await retriever.retrieve("error", user2_id, top_k=10)
        assert len(results_user2_error) == 0  # Should find no documents

    @pytest.mark.asyncio
    async def test_retrieve_fuzzy_matching(self, indexer, fuzzy_retriever, test_documents):
        """Test fuzzy matching with misspelled terms."""
        user_id = test_documents[0].user_id

        # Add a document with potential misspellings
        fuzzy_doc = Document(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type="test",
            content_hash="fuzzy_hash",
            content="This document contains misspelled words like recieve and acommodate",
            metadata={},
        )
        await indexer.index_document(fuzzy_doc)

        # Search with misspelled term (should find document via fuzzy matching)
        results = await fuzzy_retriever.retrieve("recieve", user_id, top_k=3)

        # Should find the document despite misspelling
        assert len(results) >= 1
        found = any(
            "recieve" in result["content"] or "receive" in result["content"] for result in results
        )
        assert found

    @pytest.mark.asyncio
    async def test_retrieve_explain_analyze_uses_index(self, indexer, retriever, test_documents):
        """Test that queries use the GIN index (not sequential scan)."""
        user_id = test_documents[0].user_id

        await indexer.index_documents_batch(test_documents)

        # Test query with EXPLAIN ANALYZE
        async with retriever._pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                EXPLAIN (ANALYZE, BUFFERS) 
                SELECT id FROM documents 
                WHERE search_vector @@ websearch_to_tsquery('english', 'error code')
                AND user_id = $1
            """,
                user_id,
            )

            explain_text = str(result["explain"])
            # Should use GIN index, not sequential scan
            assert "Bitmap Heap Scan" in explain_text or "Index Scan" in explain_text
            assert "Seq Scan" not in explain_text or "Bitmap Heap Scan" in explain_text

    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self, indexer, retriever, test_documents):
        """Test retrieval with no matching results."""
        user_id = test_documents[0].user_id

        await indexer.index_documents_batch(test_documents)

        # Search for non-existent term
        results = await retriever.retrieve("nonexistent_term_xyz", user_id, top_k=10)

        # Should return empty list
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_top_k_limit(self, indexer, retriever, test_documents):
        """Test that top_k parameter properly limits results."""
        user_id = test_documents[0].user_id

        await indexer.index_documents_batch(test_documents)

        # Request only 2 documents
        results = await retriever.retrieve("error", user_id, top_k=2)

        # Should return at most 2 documents
        assert len(results) <= 2

        # Should be sorted by score (highest first)
        if len(results) > 1:
            assert results[0]["score"] >= results[1]["score"]

    @pytest.mark.asyncio
    async def test_retrieve_metadata_preservation(self, indexer, retriever, test_documents):
        """Test that metadata is preserved in retrieval results."""
        user_id = test_documents[0].user_id

        await indexer.index_documents_batch(test_documents)

        results = await retriever.retrieve("error", user_id, top_k=3)

        # Metadata should be preserved
        for result in results:
            assert "metadata" in result
            assert isinstance(result["metadata"], dict)
            assert "title" in result["metadata"]
            assert "category" in result["metadata"]
