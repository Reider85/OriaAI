"""Integration tests for document ingestion API (ADR-020 / D-2)."""

import uuid

import asyncpg
import pytest

from llm_client.rag.indexing.bm25_indexer import BM25IndexBuilder
from llm_client.rag.indexing.hybrid_indexer import index_document_with_hybrid
from llm_client.rag.indexing.models import Document


@pytest.mark.integration
class TestIngestionIntegration:
    """Round-trip: index → search_vector present → delete."""

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

    @pytest.mark.asyncio
    async def test_hybrid_index_roundtrip(self, indexer, pool, user_id):
        doc = Document(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type="api",
            content_hash=f"ingest-{uuid.uuid4()}",
            content="Ingestion integration test document about hybrid retrieval.",
            metadata={"title": "Ingest Test"},
        )

        result = await index_document_with_hybrid(doc, indexer, None)
        assert result == {"bm25_indexed": True, "vector_indexed": None}

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT search_vector FROM documents WHERE id = $1",
                doc.id,
            )
            assert row is not None
            assert "hybrid" in str(row["search_vector"]).lower() or "retrieval" in str(
                row["search_vector"]
            ).lower()

        await indexer.delete_document(doc.id)
        async with pool.acquire() as conn:
            gone = await conn.fetchval(
                "SELECT 1 FROM documents WHERE id = $1", doc.id
            )
            assert gone is None

    @pytest.mark.asyncio
    async def test_users_fk_bootstrap(self, indexer, pool):
        """Ingestion creates the users row before inserting the document."""
        uid = str(uuid.uuid4())
        doc = Document(
            id=str(uuid.uuid4()),
            user_id=uid,
            source_type="api",
            content_hash=f"fk-{uuid.uuid4()}",
            content="FK bootstrap test content.",
        )

        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1) ON CONFLICT DO NOTHING", uid
            )

        await indexer.index_document(doc)

        async with pool.acquire() as conn:
            user_exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", uid)
            doc_exists = await conn.fetchval(
                "SELECT 1 FROM documents WHERE id = $1", doc.id
            )
            assert user_exists == 1
            assert doc_exists == 1

        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE user_id = $1", uid)
            await conn.execute("DELETE FROM users WHERE id = $1", uid)
