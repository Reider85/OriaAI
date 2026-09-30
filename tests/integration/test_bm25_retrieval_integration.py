"""Integration tests for BM25Retriever with real PostgreSQL."""

import json
import uuid

import asyncpg
import pytest

from llm_client.rag.indexing.bm25_indexer import BM25IndexBuilder
from llm_client.rag.indexing.models import Document
from llm_client.rag.retrieval.bm25_retriever import BM25Retriever


async def _ensure_user(pool: asyncpg.Pool, user_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id) VALUES ($1) ON CONFLICT DO NOTHING", user_id
        )


@pytest.mark.integration
class TestBM25RetrievalIntegration:
    """Integration tests for BM25Retriever with real PostgreSQL."""

    @pytest.fixture
    async def pool(self, database_url):
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        yield pool
        await pool.close()

    @pytest.fixture
    async def indexer(self, pool):
        return BM25IndexBuilder(pool, text_search_config="english")

    @pytest.fixture
    async def retriever(self, pool):
        return BM25Retriever(pool, text_search_config="english", fuzzy_enabled=False)

    @pytest.fixture
    async def fuzzy_retriever(self, pool):
        return BM25Retriever(pool, text_search_config="english", fuzzy_enabled=True)

    @pytest.fixture
    async def test_documents(self, pool):
        docs = [
            Document(
                id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                source_type="test",
                content_hash=f"hash-{uuid.uuid4()}",
                content=(
                    "Error code 1234: This document contains important error "
                    "information about system failures and troubleshooting steps "
                    "for network connectivity issues."
                ),
                metadata={"title": f"Error Document {i}", "category": "system"},
            )
            for i in range(5)
        ]
        for doc in docs:
            await _ensure_user(pool, doc.user_id)
        yield docs
        async with pool.acquire() as conn:
            for doc in docs:
                await conn.execute(
                    "DELETE FROM documents WHERE user_id = $1", doc.user_id
                )
                await conn.execute("DELETE FROM users WHERE id = $1", doc.user_id)

    @pytest.mark.asyncio
    async def test_retrieve_exact_match(self, indexer, retriever, test_documents):
        user_id = test_documents[0].user_id
        await indexer.index_documents_batch(test_documents)

        results = await retriever.retrieve("error code 1234", user_id, top_k=3)

        assert len(results) >= 1
        found = any("Error code 1234" in result["content"] for result in results)
        assert found
        for result in results:
            assert "score" in result
            assert "snippet" in result
            assert isinstance(result["score"], float)
            assert result["score"] > 0

    @pytest.mark.asyncio
    async def test_retrieve_with_snippet_highlighting(self, indexer, retriever, test_documents):
        user_id = test_documents[0].user_id
        await indexer.index_documents_batch(test_documents)

        results = await retriever.retrieve("error code 1234", user_id, top_k=3)
        assert len(results) >= 1
        assert any("<b>" in r["snippet"] for r in results)

    @pytest.mark.asyncio
    async def test_retrieve_user_isolation(self, indexer, retriever, pool, test_documents):
        user_a = test_documents[0].user_id
        user_b = str(uuid.uuid4())
        await _ensure_user(pool, user_b)

        doc_b = Document(
            id=str(uuid.uuid4()),
            user_id=user_b,
            source_type="test",
            content_hash=f"hash-b-{uuid.uuid4()}",
            content="Error code 9999: unique marker for user B isolation test.",
        )
        await indexer.index_documents_batch([doc_b, test_documents[0]])

        results_a = await retriever.retrieve("error code", user_a, top_k=10)
        results_b = await retriever.retrieve("error code 9999", user_b, top_k=10)

        assert all("9999" not in r["content"] for r in results_a)
        assert any("9999" in r["content"] for r in results_b)

        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE user_id = $1", user_b)
            await conn.execute("DELETE FROM users WHERE id = $1", user_b)

    @pytest.mark.asyncio
    async def test_retrieve_fuzzy_matching(self, indexer, fuzzy_retriever, pool):
        user_id = str(uuid.uuid4())
        await _ensure_user(pool, user_id)
        fuzzy_doc = Document(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type="test",
            content_hash=f"fuzzy-{uuid.uuid4()}",
            content="The quick brown fox jumps over the lazy dog near the riverbank",
        )
        await indexer.index_document(fuzzy_doc)

        async with pool.acquire() as conn:
            await conn.execute("SET pg_trgm.similarity_threshold = 0.05")

        results = await fuzzy_retriever.retrieve("quik brown fox", user_id, top_k=5)
        assert len(results) >= 1

        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

    @pytest.mark.asyncio
    async def test_retrieve_explain_analyze_uses_index(self, indexer, retriever, pool, test_documents):
        user_id = test_documents[0].user_id
        await indexer.index_documents_batch(test_documents)

        async with pool.acquire() as conn:
            await conn.execute("SET enable_seqscan = off")
            rows = await conn.fetch(
                """
                EXPLAIN
                SELECT id FROM documents
                WHERE search_vector @@ websearch_to_tsquery('english', 'error code')
                  AND user_id = $1
                """,
                user_id,
            )
        plan = "\n".join(row[0] for row in rows)
        assert "Bitmap" in plan or "Index" in plan

    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self, indexer, retriever, test_documents):
        user_id = test_documents[0].user_id
        await indexer.index_documents_batch(test_documents)
        results = await retriever.retrieve("xyzzy-nonexistent-term", user_id, top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_top_k_limit(self, indexer, retriever, test_documents):
        user_id = test_documents[0].user_id
        await indexer.index_documents_batch(test_documents)
        results = await retriever.retrieve("error", user_id, top_k=2)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_retrieve_metadata_preservation(self, indexer, retriever, test_documents):
        user_id = test_documents[0].user_id
        await indexer.index_documents_batch(test_documents)
        results = await retriever.retrieve("error code 1234", user_id, top_k=5)
        assert len(results) >= 1
        meta = results[0]["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert "title" in meta or "category" in meta
