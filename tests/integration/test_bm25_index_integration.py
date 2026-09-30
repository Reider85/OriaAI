"""Integration tests for BM25IndexBuilder with real PostgreSQL."""

import asyncio
import uuid

import asyncpg
import pytest

from llm_client.rag.indexing.bm25_indexer import BM25IndexBuilder
from llm_client.rag.indexing.models import Document


@pytest.mark.integration
class TestBM25IndexIntegration:
    """Integration tests for BM25IndexBuilder with real PostgreSQL."""

    @pytest.fixture
    async def pool(self, database_url):
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        yield pool
        await pool.close()

    @pytest.fixture
    async def indexer(self, pool):
        return BM25IndexBuilder(pool, text_search_config="english")

    @pytest.fixture
    async def user_id(self, pool):
        uid = str(uuid.uuid4())
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO users (id) VALUES ($1)", uid)
        yield uid
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE user_id = $1", uid)
            await conn.execute("DELETE FROM users WHERE id = $1", uid)

    @pytest.fixture
    def test_documents(self, user_id):
        return [
            Document(
                id=str(uuid.uuid4()),
                user_id=user_id,
                source_type="test",
                content_hash=f"hash-{uuid.uuid4()}",
                content=(
                    f"Test document content {i}. This is some sample text "
                    "for testing BM25 indexing functionality."
                ),
                metadata={"title": f"Test Doc {i}", "category": "test"},
            )
            for i in range(5)
        ]

    @pytest.mark.asyncio
    async def test_index_document_roundtrip(self, indexer, test_documents):
        doc = test_documents[0]

        await indexer.index_document(doc)

        async with indexer.pg_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT id, content, metadata, search_vector FROM documents WHERE id = $1",
                doc.id,
            )

            assert result is not None
            assert result["id"] == uuid.UUID(doc.id)
            assert result["content"] == doc.content
            meta = result["metadata"]
            if isinstance(meta, str):
                import json

                meta = json.loads(meta)
            assert meta == doc.metadata
            assert result["search_vector"] is not None
            assert "test" in str(result["search_vector"]).lower()

    @pytest.mark.asyncio
    async def test_index_document_upsert(self, indexer, test_documents):
        doc = test_documents[0]

        await indexer.index_document(doc)

        doc.content = "Updated document content"
        await indexer.index_document(doc)

        async with indexer.pg_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT content FROM documents WHERE id = $1",
                doc.id,
            )
            assert result["content"] == "Updated document content"

    @pytest.mark.asyncio
    async def test_search_vector_recomputed_on_update(self, indexer, test_documents):
        """GENERATED ALWAYS AS STORED must recompute search_vector on content UPDATE."""
        doc = test_documents[0]
        doc.content = "alpha beta gamma initial content"
        await indexer.index_document(doc)

        async with indexer.pg_pool.acquire() as conn:
            before = await conn.fetchval(
                "SELECT search_vector::text FROM documents WHERE id = $1", doc.id
            )
            assert "alpha" in before

        doc.content = "delta epsilon zeta updated content"
        await indexer.index_document(doc)

        async with indexer.pg_pool.acquire() as conn:
            after = await conn.fetchval(
                "SELECT search_vector::text FROM documents WHERE id = $1", doc.id
            )
            assert "delta" in after
            assert "alpha" not in after

    @pytest.mark.asyncio
    async def test_delete_document(self, indexer, test_documents):
        doc = test_documents[0]
        await indexer.index_document(doc)
        await indexer.delete_document(doc.id)

        async with indexer.pg_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT id FROM documents WHERE id = $1",
                doc.id,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_batch_indexing(self, indexer, test_documents):
        await indexer.index_documents_batch(test_documents)

        async with indexer.pg_pool.acquire() as conn:
            for doc in test_documents:
                result = await conn.fetchrow(
                    "SELECT id FROM documents WHERE id = $1",
                    doc.id,
                )
                assert result is not None

    @pytest.mark.asyncio
    async def test_search_vector_generation(self, indexer, test_documents):
        doc = test_documents[0]
        await indexer.index_document(doc)

        async with indexer.pg_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT search_vector FROM documents WHERE id = $1",
                doc.id,
            )
            search_vector = result["search_vector"]
            assert search_vector is not None
            search_text = str(search_vector)
            assert "test" in search_text.lower() or "document" in search_text.lower()

    @pytest.mark.asyncio
    async def test_explain_analyze_uses_index(self, indexer, test_documents):
        doc = test_documents[0]
        await indexer.index_document(doc)

        async with indexer.pg_pool.acquire() as conn:
            await conn.execute("SET enable_seqscan = off")
            rows = await conn.fetch(
                """
                EXPLAIN
                SELECT id FROM documents
                WHERE search_vector @@ websearch_to_tsquery('english', 'test document')
                AND user_id = $1
                """,
                doc.user_id,
            )
            explain_text = "\n".join(row[0] for row in rows)
            assert "Bitmap" in explain_text or "Index" in explain_text

    @pytest.mark.asyncio
    async def test_fuzzy_search_support(self, indexer, user_id):
        doc = Document(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type="test",
            content_hash=f"fuzzy-{uuid.uuid4()}",
            content="The quick brown fox jumps over the lazy dog near the riverbank",
            metadata={},
        )
        await indexer.index_document(doc)

        async with indexer.pg_pool.acquire() as conn:
            await conn.execute("SET pg_trgm.similarity_threshold = 0.05")
            result = await conn.fetchrow(
                """
                SELECT id FROM documents
                WHERE content % 'quik brown fox'
                AND user_id = $1
                """,
                doc.user_id,
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_indexing(self, indexer, test_documents):
        concurrent_docs = test_documents[:3]
        await asyncio.gather(*[indexer.index_document(doc) for doc in concurrent_docs])

        async with indexer.pg_pool.acquire() as conn:
            for doc in concurrent_docs:
                result = await conn.fetchrow(
                    "SELECT id FROM documents WHERE id = $1",
                    doc.id,
                )
                assert result is not None
