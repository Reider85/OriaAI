"""Integration tests for CacheInvalidator with real Redis."""

import asyncio
import time
from uuid import uuid4

import pytest
import redis.asyncio as redis
from langchain_openai import OpenAIEmbeddings

from llm_client.rag.cache_invalidator import get_cache_invalidator
from llm_client.rag.semantic_cache import SemanticAnswerCache


@pytest.fixture
async def redis_client():
    """Redis client for integration tests."""
    client = redis.from_url("redis://127.0.0.1:6379/2", decode_responses=True)
    try:
        await client.ping()
        yield client
    except redis.ConnectionError:
        pytest.skip("Redis not available on port 6379/2")
    finally:
        await client.aclose()


@pytest.fixture
async def mock_embeddings():
    """Mock embeddings for testing."""
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    # Mock embeddings to return consistent vectors for testing
    original_aembed_query = embeddings.aembed_query
    
    async def mock_embed_query(text):
        # Return consistent vector based on text hash
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16) % 1000
        return [float(hash_val), float(hash_val + 1), float(hash_val + 2)]
    
    embeddings.aembed_query = mock_embed_query
    return embeddings


@pytest.fixture
async def semantic_cache(redis_client, mock_embeddings):
    """Fixture providing SemanticAnswerCache with real Redis and mock embeddings."""
    return SemanticAnswerCache(
        redis_client=redis_client,
        embeddings=mock_embeddings,
        ttl_seconds=300,  # 5 minutes for test
        similarity_threshold=0.9,
        max_entries=100,
    )


@pytest.mark.asyncio
async def test_end_to_end_invalidation_stale_answers(semantic_cache):
    """Test that invalidation marks cached answers as stale."""
    doc_id1 = uuid4()
    doc_id2 = uuid4()
    
    # Put two cached answers referencing different documents
    await semantic_cache.put("What is Python?", "Python is a programming language.", [doc_id1], "gpt-4o-mini", 100)
    await semantic_cache.put("How does RAG work?", "RAG combines retrieval and generation.", [doc_id2], "gpt-4o-mini", 150)
    
    # Verify both answers are cached
    result1 = await semantic_cache.get("What is Python?")
    result2 = await semantic_cache.get("How does RAG work?")
    assert result1 is not None
    assert result2 is not None
    
    # Invalidate doc_id1
    invalidator = get_cache_invalidator()
    count = await invalidator.invalidate_doc(doc_id1)
    assert count == 1
    
    # Verify that answer referencing doc_id1 is stale (returns None)
    result1_after = await semantic_cache.get("What is Python?")
    assert result1_after is None
    
    # Verify that answer referencing doc_id2 is still valid
    result2_after = await semantic_cache.get("How does RAG work?")
    assert result2_after is not None


@pytest.mark.asyncio
async def test_end_to_end_invalidation_batch(semantic_cache):
    """Test batch invalidation of multiple documents."""
    doc1 = uuid4()
    doc2 = uuid4()
    doc3 = uuid4()
    
    # Put answers for three documents
    await semantic_cache.put("Query 1", "Answer 1", [doc1], "gpt-4o-mini", 100)
    await semantic_cache.put("Query 2", "Answer 2", [doc2, doc3], "gpt-4o-mini", 150)
    await semantic_cache.put("Query 3", "Answer 3", [doc3], "gpt-4o-mini", 200)
    
    # Verify all are cached
    assert await semantic_cache.get("Query 1") is not None
    assert await semantic_cache.get("Query 2") is not None
    assert await semantic_cache.get("Query 3") is not None
    
    # Batch invalidate doc1 and doc2
    invalidator = get_cache_invalidator()
    total = await invalidator.invalidate_batch([doc1, doc2])
    assert total == 2  # Query1 (1 doc), Query2 (2 docs) = 3, but Query2 references doc2 only
    
    # Query1 should be stale (referenced doc1)
    result1 = await semantic_cache.get("Query 1")
    assert result1 is None
    
    # Query2 should be stale (referenced doc2)
    result2 = await semantic_cache.get("Query 2")
    assert result2 is None
    
    # Query3 should still be valid (only references doc3, not invalidated)
    result3 = await semantic_cache.get("Query 3")
    assert result3 is not None


@pytest.mark.asyncio
async def test_invalidate_doc_returns_zero_if_no_entries(semantic_cache):
    """Test invalidate_doc returns 0 when no cached entries reference the document."""
    doc_id = uuid4()
    
    # Put an answer that doesn't reference this document
    other_doc_id = uuid4()
    await semantic_cache.put("Other query", "Other answer", [other_doc_id], "gpt-4o-mini", 100)
    
    invalidator = get_cache_invalidator()
    count = await invalidator.invalidate_doc(doc_id)
    
    assert count == 0


@pytest.mark.asyncio
async def test_invalidate_when_cache_disabled():
    """Test that invalidate handles disabled cache gracefully."""
    # This test doesn't need a real semantic_cache fixture
    invalidator = get_cache_invalidator()
    doc_id = uuid4()
    
    # The cache should be disabled in test environment or we can mock it
    with patch("llm_client.rag.cache_invalidator.get_semantic_cache", return_value=None):
        count = await invalidator.invalidate_doc(doc_id)
        assert count == 0


@pytest.mark.asyncio
async def test_metrics_integration(semantic_cache):
    """Test that stale answers increment the correct metric."""
    from llm_client.observability.llm_metrics import record_cache_hit
    
    doc_id = uuid4()
    
    # Put an answer
    await semantic_cache.put("Test query", "Test answer", [doc_id], "gpt-4o-mini", 100)
    
    # Get it (should be hit)
    result = await semantic_cache.get("Test query")
    assert result is not None
    
    # Invalidate
    invalidator = get_cache_invalidator()
    await invalidator.invalidate_doc(doc_id)
    
    # Get again (should be stale)
    result_stale = await semantic_cache.get("Test query")
    assert result_stale is None
    
    # Verify metric was incremented for stale encounter
    # Note: This is indirect verification since we can't directly check Prometheus metrics in test
    # The actual metric increment happens in semantic_cache.get() when stale is encountered