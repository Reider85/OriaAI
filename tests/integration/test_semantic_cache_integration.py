"""Integration tests for SemanticAnswerCache with real Redis."""

import asyncio

import pytest

from llm_client.rag.semantic_cache import SemanticAnswerCache, get_semantic_cache


class MockOpenAIEmbeddings:
    """Mock OpenAIEmbeddings for integration tests."""

    def __init__(self):
        self.vector_db = {
            "hello": [0.1, 0.2, 0.3] * 512,
            "what is python": [0.7, 0.8, 0.9] * 512,
            "what is the python language": [0.71, 0.81, 0.91] * 512,
        }

    async def aembed_query(self, query: str) -> list[float]:
        return self.vector_db.get(query, [0.0] * 1536)


@pytest.fixture
async def redis_client():
    """Fixture providing real Redis client for DB 2."""
    import redis.asyncio as aioredis
    from redis.exceptions import ConnectionError as RedisConnectionError

    from llm_client.config import settings

    redis_url = settings.redis_semantic_cache_url

    client = aioredis.from_url(redis_url, decode_responses=False)
    try:
        # Test connection
        await client.ping()
        yield client
    except (RedisConnectionError, OSError) as e:
        pytest.skip(f"Redis not available at {redis_url}: {e}")
    finally:
        await client.aclose()


@pytest.fixture
def mock_embeddings():
    """Fixture providing mock embeddings."""
    return MockOpenAIEmbeddings()


@pytest.fixture
def semantic_cache(redis_client, mock_embeddings):
    """Fixture providing SemanticAnswerCache with real Redis and mock embeddings."""
    return SemanticAnswerCache(
        redis_client=redis_client,
        embeddings=mock_embeddings,
        ttl_seconds=86400,
        similarity_threshold=0.92,
        max_entries=10000,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_semantic_cache_hit(semantic_cache):
    """Test end-to-end semantic cache with real Redis - hit scenario."""
    doc_id = "123e4567-e89b-12d3-a456-426614174000"

    # Put a query in cache
    await semantic_cache.put(
        "what is python",
        "Python is a high-level programming language known for its simplicity.",
        [doc_id],
        "gpt-4o-mini",
        50,
    )

    # Get exact match
    result = await semantic_cache.get("what is python")
    assert result is not None
    assert result.answer == "Python is a high-level programming language known for its simplicity."
    assert result.referenced_doc_ids == [doc_id]
    assert result.model == "gpt-4o-mini"
    assert result.token_count == 50
    assert result.similarity_score >= 0.99


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_semantic_cache_paraphrase_hit(semantic_cache):
    """Test end-to-end semantic cache with real Redis - paraphrase hit scenario."""
    doc_id = "123e4567-e89b-12d3-a456-426614174001"

    # Put a query in cache
    await semantic_cache.put(
        "what is python",
        "Python is a programming language that emphasizes code readability.",
        [doc_id],
        "gpt-4o-mini",
        45,
    )

    # Get with paraphrase (semantically similar)
    result = await semantic_cache.get("what is the python language")
    assert result is not None
    assert result.answer == "Python is a programming language that emphasizes code readability."
    assert result.referenced_doc_ids == [doc_id]
    assert result.similarity_score > 0.92  # semantic hit, not exact
    assert result.similarity_score < 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_semantic_cache_miss(semantic_cache):
    """Test end-to-end semantic cache with real Redis - miss scenario."""
    # Put a query
    doc_id = "123e4567-e89b-12d3-a456-426614174002"
    await semantic_cache.put("hello", "Hello world!", [doc_id], "gpt-4o-mini", 10)

    # Query with different semantics
    result = await semantic_cache.get("completely unrelated topic")
    assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_cache_mark_stale(semantic_cache):
    """Test end-to-end mark_stale with real Redis."""
    doc_id = "123e4567-e89b-12d3-a456-426614174003"

    # Put multiple queries referencing the same doc
    await semantic_cache.put("query1", "Answer 1", [doc_id], "gpt-4o-mini", 100)
    await semantic_cache.put("query2", "Answer 2", [doc_id, "other-doc"], "gpt-4o-mini", 150)
    await semantic_cache.put("query3", "Answer 3", ["other-doc"], "gpt-4o-mini", 200)

    # Mark doc_id as stale
    stale_count = await semantic_cache.mark_stale(doc_id)
    assert stale_count == 2  # query1 and query2 reference doc_id

    # Query1 and query2 should now be stale (return None)
    result1 = await semantic_cache.get("query1")
    assert result1 is None

    result2 = await semantic_cache.get("query2")
    assert result2 is None

    # Query3 should still work
    result3 = await semantic_cache.get("query3")
    assert result3 is not None
    assert result3.answer == "Answer 3"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_cache_ttl_expiry(semantic_cache):
    """Test end-to-end TTL expiry with real Redis."""
    doc_id = "123e4567-e89b-12d3-a456-426614174004"

    # put() has no per-call ttl — use a short-TTL cache instance
    short_ttl_cache = SemanticAnswerCache(
        redis_client=semantic_cache._redis,
        embeddings=semantic_cache._embeddings,
        ttl_seconds=2,
        similarity_threshold=0.92,
        max_entries=10000,
    )

    # Put with short TTL (2 seconds)
    await short_ttl_cache.put(
        "temporary",
        "This will expire soon",
        [doc_id],
        "gpt-4o-mini",
        20,
    )

    # Should hit immediately
    result = await short_ttl_cache.get("temporary")
    assert result is not None

    # Wait for expiry
    await asyncio.sleep(2.1)

    # Should miss after expiry
    result = await short_ttl_cache.get("temporary")
    assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_singleton_factory_integration():
    """Test get_semantic_cache() singleton with real Redis."""
    from urllib.parse import urlparse

    from llm_client.config import settings

    # First call creates singleton
    cache1 = get_semantic_cache()
    assert cache1 is not None

    # Verify it uses real Redis from settings
    assert cache1._redis is not None
    expected_host = urlparse(settings.redis_semantic_cache_url).hostname
    assert expected_host in str(cache1._redis)

    # Second call returns same instance
    cache2 = get_semantic_cache()
    assert cache1 is cache2

    # Test close
    await cache1.close()

    # Reopening should work
    cache3 = get_semantic_cache()
    assert cache3 is not None
    assert cache1 is not cache3  # new instance after close


@pytest.mark.integration
@pytest.mark.asyncio
async def test_metrics_integration(semantic_cache):
    """Test that metrics are recorded with real Redis."""
    from llm_client.observability.llm_metrics import SEMANTIC_CACHE_HITS

    doc_id = "123e4567-e89b-12d3-a456-426614174005"

    # Record initial metric values
    initial_hit = SEMANTIC_CACHE_HITS.labels(status="hit")._value.get()
    initial_miss = SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()

    # Put and get
    await semantic_cache.put("test-query", "Test answer", [doc_id], "gpt-4o-mini", 100)
    await semantic_cache.get("test-query")  # hit

    await semantic_cache.get("non-existent")  # miss

    # Check metric deltas
    final_hit = SEMANTIC_CACHE_HITS.labels(status="hit")._value.get()
    final_miss = SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()

    assert final_hit - initial_hit == 1
    assert final_miss - initial_miss == 1
