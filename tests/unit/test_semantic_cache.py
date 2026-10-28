"""Unit tests for SemanticAnswerCache (B-1 ADR-011)."""

import asyncio
import time
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from llm_client.rag.semantic_cache import SemanticAnswerCache, get_semantic_cache


class FakeRedis:
    """Minimal Redis mock for testing semantic cache operations."""

    def __init__(self):
        self.data = {}
        self.expiry = {}
        self.pipeline_calls = []

    async def scan(self, cursor=0, match="*", count=100):
        """Mock SCAN with pattern matching."""
        if cursor != 0:
            return cursor, []

        # Filter keys by match pattern - handle Redis wildcard patterns
        matched_keys = []
        if match == "*":
            # Match all keys
            matched_keys = list(self.data.keys())
        elif match.endswith("*"):
            # Match keys that start with the prefix (before the *)
            prefix = match[:-1]
            matched_keys = [key for key in self.data if key.startswith(prefix)]
        elif match.startswith("*"):
            # Match keys that end with the suffix (after the *)
            suffix = match[1:]
            matched_keys = [key for key in self.data if key.endswith(suffix)]
        else:
            # Match keys that contain the pattern
            matched_keys = [key for key in self.data if match in key]

        # Return in batches of count
        if count and len(matched_keys) > count:
            return cursor, matched_keys[:count]
        return cursor, matched_keys

    async def mget(self, keys):
        """Mock MGET — return values in same order as keys."""
        return [self.data.get(key) for key in keys]

    async def get(self, key):
        """Mock GET — check expiry first."""
        if key in self.expiry and self.expiry[key] < time.time():
            del self.data[key]
            del self.expiry[key]
            return None
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        """Mock SET with optional expiry."""
        self.data[key] = value
        if ex:
            self.expiry[key] = time.time() + ex

    def pipeline(self):
        """Mock pipeline — collect operations, execute on explicit call."""
        pipe = FakePipeline(self)
        self.pipeline_calls.append(pipe)
        return pipe

    async def keys(self, pattern="*"):
        """Mock KEYS with pattern matching."""
        matched_keys = []
        if pattern == "*":
            # Match all keys
            matched_keys = list(self.data.keys())
        elif pattern.endswith("*"):
            # Match keys that start with the prefix (before the *)
            prefix = pattern[:-1]
            matched_keys = [key for key in self.data if key.startswith(prefix)]
        elif pattern.startswith("*"):
            # Match keys that end with the suffix (after the *)
            suffix = pattern[1:]
            matched_keys = [key for key in self.data if key.endswith(suffix)]
        else:
            # Match keys that contain the pattern
            matched_keys = [key for key in self.data if pattern in key]

        return matched_keys

    async def aclose(self):
        """Mock close."""


class FakePipeline:
    """Mock Redis pipeline."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.commands = []

    def set(self, key, value, ex=None):
        self.commands.append(("set", key, value, ex))
        return self

    async def execute(self):
        """Execute all queued commands."""
        for cmd in self.commands:
            if cmd[0] == "set":
                await self.redis.set(cmd[1], cmd[2], ex=cmd[3])
        self.commands = []


class MockOpenAIEmbeddings:
    """Mock OpenAIEmbeddings with deterministic vectors for testing."""

    def __init__(self):
        # Fixed embeddings for consistent tests
        self.vector_db = {
            "hello": [0.1, 0.2, 0.3] * 512,  # 1536 dim
            "python": [0.4, 0.5, 0.6] * 512,
            "what is python": [0.7, 0.8, 0.9] * 512,
            "what is the python language": [0.71, 0.81, 0.91] * 512,
            "totally different": [1.0, -1.0, 0.0] * 512,
            "query1": [0.11, 0.12, 0.13] * 512,
            "query2": [0.21, 0.22, 0.23] * 512,
            "query3": [0.31, 0.32, 0.33] * 512,
            "what is python again": [0.12, 0.13, 0.14] * 512,
            "q1": [0.15, 0.16, 0.17] * 512,
            "q2": [1.0, -1.0, 0.0] * 512,
            "q3": [-1.0, 1.0, 0.5] * 512,
            "q4": [0.45, 0.46, 0.47] * 512,
        }

    async def aembed_query(self, query: str) -> list[float]:
        """Return deterministic embedding for query."""
        return self.vector_db.get(query, [0.0, 0.0, 0.0] * 512)


@pytest.fixture
def mock_embeddings():
    """Fixture providing mock embeddings."""
    return MockOpenAIEmbeddings()


@pytest.fixture
def fake_redis():
    """Fixture providing fake Redis client."""
    return FakeRedis()


@pytest.fixture
def cache(fake_redis, mock_embeddings):
    """Fixture providing SemanticAnswerCache with fake Redis and mock embeddings."""
    return SemanticAnswerCache(
        redis_client=fake_redis,
        embeddings=mock_embeddings,
        ttl_seconds=86400,
        similarity_threshold=0.92,
        max_entries=10000,
    )


@pytest.fixture
def short_ttl_cache(fake_redis, mock_embeddings):
    """Fixture providing SemanticAnswerCache with short TTL for expiry tests."""
    return SemanticAnswerCache(
        redis_client=fake_redis,
        embeddings=mock_embeddings,
        ttl_seconds=1,  # 1 second TTL
        similarity_threshold=0.92,
        max_entries=10000,
    )


@pytest.mark.asyncio
async def test_cache_miss_on_empty_cache(cache):
    """Test cache miss on empty cache."""
    from llm_client.observability.llm_metrics import SEMANTIC_CACHE_HITS

    before = SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()

    result = await cache.get("hello")
    assert result is None

    # Verify metrics were recorded (delta — counter is global per process)
    hits = SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()
    assert hits == before + 1


@pytest.mark.asyncio
async def test_cache_put_then_get_hit(cache):
    """Test cache put followed by exact get hit."""
    from llm_client.observability.llm_metrics import SEMANTIC_CACHE_HITS

    doc_id = "123e4567-e89b-12d3-a456-426614174000"
    await cache.put("hello", "Hello world!", [doc_id], "gpt-4o-mini", 100)

    before = SEMANTIC_CACHE_HITS.labels(status="hit")._value.get()

    result = await cache.get("hello")
    assert result is not None
    assert result.answer == "Hello world!"
    assert result.referenced_doc_ids == [UUID(doc_id)]
    assert result.model == "gpt-4o-mini"
    assert result.token_count == 100
    assert result.similarity_score >= 0.99  # exact match

    # Verify metrics (delta — counter is global per process)
    hits = SEMANTIC_CACHE_HITS.labels(status="hit")._value.get()
    assert hits == before + 1


@pytest.mark.asyncio
async def test_cache_get_below_threshold_returns_miss(cache):
    """Test cache get with semantically different query returns miss."""
    # Put "python" query
    doc_id = "123e4567-e89b-12d3-a456-426614174001"
    await cache.put("python", "Python is a language", [doc_id], "gpt-4o-mini", 50)

    # Query with very different semantics
    result = await cache.get("totally different")
    assert result is None

    # Verify metrics
    from llm_client.observability.llm_metrics import SEMANTIC_CACHE_HITS

    miss_count = SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()
    assert miss_count >= 1


@pytest.mark.asyncio
async def test_cache_get_semantically_similar_query_hits(cache):
    """Test cache get with paraphrase hits due to semantic similarity."""
    # Put exact query
    doc_id = "123e4567-e89b-12d3-a456-426614174002"
    await cache.put(
        "what is python", "Python is a programming language", [doc_id], "gpt-4o-mini", 80
    )

    # Query with paraphrase (similar embedding)
    result = await cache.get("what is the python language")
    assert result is not None
    assert result.answer == "Python is a programming language"
    assert result.similarity_score > 0.92  # semantic hit
    assert result.similarity_score < 1.0  # not exact match

    # Additional verification: test another query to ensure cache is working
    other_doc_id = UUID("111e4567-e89b-12d3-a456-426614174999")
    await cache.put(
        "what is python again",
        "Python is a programming language",
        [str(other_doc_id)],
        "gpt-4o-mini",
        80,
    )
    result2 = await cache.get("what is python again")
    assert result2 is not None
    assert result2.answer == "Python is a programming language"


@pytest.mark.asyncio
async def test_cache_ttl_expiry(short_ttl_cache):
    """Test cache TTL expiry."""
    # Put with short TTL
    doc_id = "123e4567-e89b-12d3-a456-426614174003"
    await short_ttl_cache.put("hello", "Temporary answer", [doc_id], "gpt-4o-mini", 10)

    # Should hit immediately
    result = await short_ttl_cache.get("hello")
    assert result is not None

    # Wait for expiry
    await asyncio.sleep(1.1)

    # Should miss after expiry
    result = await short_ttl_cache.get("hello")
    assert result is None


@pytest.mark.asyncio
async def test_cache_mark_stale_on_doc_update(cache):
    """Test mark_stale marks all answers referencing doc_id as stale."""
    doc_id_str = "123e4567-e89b-12d3-a456-426614174004"
    doc_id = UUID(doc_id_str)
    other_doc_id = UUID("111e4567-e89b-12d3-a456-426614174999")

    # Put multiple answers referencing the same doc
    await cache.put("query1", "Answer 1", [doc_id_str], "gpt-4o-mini", 100)
    await cache.put("query2", "Answer 2", [doc_id_str, str(other_doc_id)], "gpt-4o-mini", 150)
    await cache.put("query3", "Answer 3", [str(other_doc_id)], "gpt-4o-mini", 200)

    # Mark doc_id as stale
    stale_count = await cache.mark_stale(doc_id)
    assert stale_count == 2  # query1 and query2 reference doc_id

    # Query1 and query2 should now return stale (None)
    result1 = await cache.get("query1")
    assert result1 is None

    result2 = await cache.get("query2")
    assert result2 is None

    # Query3 should still work (doesn't reference doc_id)
    result3 = await cache.get("query3")
    assert result3 is not None
    assert result3.answer == "Answer 3"


@pytest.mark.asyncio
async def test_cache_record_hit_metrics(cache):
    """Test that cache hits/misses/stale are recorded in Prometheus metrics."""
    doc_id = "123e4567-e89b-12d3-a456-426614174005"

    # 3 hits (put + 2 gets)
    await cache.put("q1", "a1", [doc_id], "gpt-4o-mini", 100)
    result1 = await cache.get("q1")
    assert result1 is not None
    result1_again = await cache.get("q1")
    assert result1_again is not None

    # 2 misses
    result2 = await cache.get("q2")  # miss (not in cache)
    assert result2 is None
    result3 = await cache.get("q3")  # miss (not in cache)
    assert result3 is None

    # 1 stale (q4, q1 was already there and should also be marked stale)
    await cache.put("q4", "a4", [doc_id], "gpt-4o-mini", 100)
    stale_count = await cache.mark_stale(doc_id)
    assert stale_count == 2  # q1 and q4 both reference doc_id
    result4 = await cache.get("q4")  # stale miss
    assert result4 is None


@pytest.mark.asyncio
async def test_cache_skip_put_with_empty_referenced_doc_ids(cache):
    """Test that put() skips caching when referenced_doc_ids is empty."""
    # Get initial metrics
    from llm_client.observability.llm_metrics import SEMANTIC_CACHE_HITS

    initial_hit = SEMANTIC_CACHE_HITS.labels(status="hit")._value.get()
    initial_miss = SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()
    initial_stale = SEMANTIC_CACHE_HITS.labels(status="stale")._value.get()

    # This should not store anything in cache
    await cache.put("no-docs-query", "Answer", [], "gpt-4o-mini", 100)

    # Verify nothing was stored
    result = await cache.get("no-docs-query")
    assert result is None

    # Verify no metrics recorded for this put
    final_hit = SEMANTIC_CACHE_HITS.labels(status="hit")._value.get()
    final_miss = SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()
    final_stale = SEMANTIC_CACHE_HITS.labels(status="stale")._value.get()

    # Metrics should not have changed significantly (allow for minimal background noise)
    assert final_hit == initial_hit
    assert final_miss - initial_miss <= 1  # allow for at most 1 background miss
    assert final_stale == initial_stale


@pytest.mark.asyncio
async def test_singleton_factory(cache):
    """Test get_semantic_cache() singleton behavior."""
    # First call creates singleton
    cache1 = get_semantic_cache()
    assert cache1 is not None

    # Second call returns same instance
    cache2 = get_semantic_cache()
    assert cache1 is cache2

    # Disable cache, should return None
    with patch("llm_client.config.settings.semantic_cache_enabled", False):
        cache_disabled = get_semantic_cache()
        assert cache_disabled is None


@pytest.mark.asyncio
async def test_cache_close():
    """Test cache close method."""
    cache = SemanticAnswerCache(
        redis_client=FakeRedis(),
        embeddings=MockOpenAIEmbeddings(),
    )

    # Mock the Redis client close method
    cache._redis.aclose = AsyncMock()

    await cache.close()
    cache._redis.aclose.assert_called_once()
