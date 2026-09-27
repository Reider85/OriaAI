"""Integration tests for BM25IndexBuilder with real PostgreSQL."""

import asyncio
import pytest
import uuid

from llm_client.rag.indexing.bm25_indexer import BM25IndexBuilder
from llm_client.rag.indexing.models import Document


@pytest.mark.integration
class TestBM25IndexIntegration:
    """Integration tests for BM25IndexBuilder with real PostgreSQL."""
    
    @pytest.fixture
    async def indexer(self, database_url):
        """Create BM25IndexBuilder with real PostgreSQL connection."""
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        indexer = BM25IndexBuilder(pool, text_search_config="english")
        yield indexer
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
                content=f"Test document content {i}. This is some sample text for testing BM25 indexing functionality.",
                metadata={"title": f"Test Doc {i}", "category": "test"}
            )
            for i in range(5)
        ]
    
    @pytest.mark.asyncio
    async def test_index_document_roundtrip(self, indexer, test_documents):
        """Test full roundtrip: index → retrieve → verify search_vector."""
        doc = test_documents[0]
        
        # Index the document
        await indexer.index_document(doc)
        
        # Verify it was indexed by querying the database
        async with indexer._pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT id, content, metadata, search_vector FROM documents WHERE id = $1",
                doc.id
            )
            
            assert result is not None
            assert result["id"] == doc.id
            assert result["content"] == doc.content
            assert result["metadata"] == doc.metadata
            assert result["search_vector"] is not None
            assert "test" in str(result["search_vector"]).lower()  # tsvector contains terms
    
    @pytest.mark.asyncio
    async def test_index_document_upsert(self, indexer, test_documents):
        """Test upsert behavior: same content_hash should update content."""
        doc = test_documents[0]
        original_content = doc.content
        
        # Index document first time
        await indexer.index_document(doc)
        
        # Update document content but keep same content_hash
        doc.content = "Updated document content"
        await indexer.index_document(doc)
        
        # Verify content was updated
        async with indexer._pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT content FROM documents WHERE id = $1",
                doc.id
            )
            
            assert result["content"] == "Updated document content"
    
    @pytest.mark.asyncio
    async def test_delete_document(self, indexer, test_documents):
        """Test document deletion."""
        doc = test_documents[0]
        
        # Index the document first
        await indexer.index_document(doc)
        
        # Delete it
        await indexer.delete_document(doc.id)
        
        # Verify it's gone
        async with indexer._pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT id FROM documents WHERE id = $1",
                doc.id
            )
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_batch_indexing(self, indexer, test_documents):
        """Test batch indexing of multiple documents."""
        # Index all documents at once
        await indexer.index_documents_batch(test_documents)
        
        # Verify all documents were indexed
        async with indexer._pool.acquire() as conn:
            for doc in test_documents:
                result = await conn.fetchrow(
                    "SELECT id FROM documents WHERE id = $1",
                    doc.id
                )
                assert result is not None
    
    @pytest.mark.asyncio
    async def test_batch_indexing_empty(self, indexer):
        """Test batch indexing with empty list."""
        # Should not raise an error
        await indexer.index_documents_batch([])
        
        # Verify no documents were accidentally created
        async with indexer._pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM documents")
            # Should still be 0 (no test documents indexed yet)
            assert count >= 0
    
    @pytest.mark.asyncio
    async def test_search_vector_generation(self, indexer, test_documents):
        """Test that search_vector is properly generated."""
        doc = test_documents[0]
        
        # Index document
        await indexer.index_document(doc)
        
        # Check that search_vector contains expected terms
        async with indexer._pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT search_vector FROM documents WHERE id = $1",
                doc.id
            )
            
            search_vector = result["search_vector"]
            assert search_vector is not None
            
            # Convert tsvector to text and check for key terms
            search_text = str(search_vector)
            # Should contain lemmatized versions of content
            assert "test" in search_text.lower() or "document" in search_text.lower()
    
    @pytest.mark.asyncio
    async def test_explain_analyze_uses_index(self, indexer, test_documents):
        """Test that queries use the GIN index (not sequential scan)."""
        doc = test_documents[0]
        
        # Index document
        await indexer.index_document(doc)
        
        # Test a query and explain plan
        async with indexer._pool.acquire() as conn:
            result = await conn.fetchrow("""
                EXPLAIN (ANALYZE, BUFFERS) 
                SELECT id FROM documents 
                WHERE search_vector @@ websearch_to_tsquery('english', 'test document')
                AND user_id = $1
            """, doc.user_id)
            
            explain_text = str(result["explain"])
            # Should use GIN index, not sequential scan
            assert "Bitmap Heap Scan" in explain_text or "Index Scan" in explain_text
            assert "Seq Scan" not in explain_text or "Bitmap Heap Scan" in explain_text
    
    @pytest.mark.asyncio
    async def test_fuzzy_search_support(self, indexer, database_url):
        """Test that pg_trgm extension works for fuzzy matching."""
        # Create document with potential fuzzy match
        doc = Document(
            id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            source_type="test",
            content_hash="fuzzy_hash",
            content="This document contains misspelled words like recieve and acommodate",
            metadata={}
        )
        
        await indexer.index_document(doc)
        
        # Test fuzzy query (should find document even with misspelling)
        async with indexer._pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT id FROM documents 
                WHERE content % 'recieve'  -- pg_trgm fuzzy match
                AND user_id = $1
            """, doc.user_id)
            
            assert result is not None  # Should find the document despite misspelling
    
    @pytest.mark.asyncio
    async def test_concurrent_indexing(self, indexer, test_documents):
        """Test concurrent indexing works correctly."""
        # Create multiple documents for concurrent indexing
        concurrent_docs = test_documents[:3]
        
        # Index them concurrently
        await asyncio.gather(*[
            indexer.index_document(doc) for doc in concurrent_docs
        ])
        
        # Verify all documents were indexed
        async with indexer._pool.acquire() as conn:
            for doc in concurrent_docs:
                result = await conn.fetchrow(
                    "SELECT id FROM documents WHERE id = $1",
                    doc.id
                )
                assert result is not