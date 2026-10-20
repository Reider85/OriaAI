"""Integration test: doc update invalidates cached answer within budget (ADR-011 pilot criterion).

Verifies full invalidation pipeline against real Redis DB 2:
- cache.put + cache.get hit
- CacheInvalidator.invalidate_doc -> SemanticAnswerCache.mark_stale
- next cache.get returns None (stale answer is never served)
- Prometheus counter semantic_cache_hits_total{status="stale"} incremented
- 100-doc batch: zero stale answers served, invalidation latency < budget

Architecture: ARCHITECT.md v1.3.0 §5.2.5 (three-tier cache).
TRIZ: principle #9 (preliminary action — invalidation before stale answer is served).
"""

import hashlib
import time
from uuid import uuid4

import numpy as np
import pytest
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError

from llm_client.config import settings
from llm_client.observability.llm_metrics import get_cache_hit_counts
from llm_client.rag import semantic_cache as semantic_cache_module
from llm_client.rag.cache_invalidator import get_cache_invalidator
from llm_client.rag.semantic_cache import get_semantic_cache

pytestmark = pytest.mark.integration


class DeterministicEmbeddings:
    """Seeded deterministic embeddings — keeps integration tests offline (no OpenAI API)."""

    DIM = 1536

    async def aembed_query(self, query: str) -> list[float]:
        seed = int(hashlib.sha256(query.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        return rng.standard_normal(self.DIM).astype(np.float32).tolist()


async def _flush_semantic_keys() -> None:
    client = aioredis.from_url(settings.redis_semantic_cache_url, decode_responses=False)
    try:
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match="sem_cache:*", count=500)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
    finally:
        await client.aclose()


@pytest.fixture
async def clean_redis():
    """Real Redis DB 2 (docker-compose); skips when unreachable. Flushes sem_cache:* keys."""
    client = aioredis.from_url(settings.redis_semantic_cache_url, decode_responses=False)
    try:
        await client.ping()
    except (RedisConnectionError, OSError) as exc:
        await client.aclose()
        pytest.skip(f"Redis not available at {settings.redis_semantic_cache_url}: {exc}")
    await client.aclose()

    await _flush_semantic_keys()
    yield
    await _flush_semantic_keys()


@pytest.fixture
async def semantic_cache(clean_redis, monkeypatch):
    """Singleton SemanticAnswerCache wired to real Redis with deterministic embeddings."""
    if not settings.semantic_cache_enabled:
        pytest.skip("SEMANTIC_CACHE_ENABLED=false")

    monkeypatch.setattr(
        semantic_cache_module,
        "OpenAIEmbeddings",
        lambda **_kwargs: DeterministicEmbeddings(),
    )
    semantic_cache_module._singleton = None

    cache = get_semantic_cache()
    assert cache is not None, "Semantic cache must be enabled for this test"
    yield cache

    await cache.close()
    semantic_cache_module._singleton = None


async def test_doc_update_invalidates_cached_answer(semantic_cache):
    """Setup: cache answer referencing doc_id. Invalidate doc. Next cache.get must return None."""
    doc_id = uuid4()
    query = f"What is in document {doc_id}?"

    before = get_cache_hit_counts()

    await semantic_cache.put(
        query=query,
        answer="Old answer based on old content",
        referenced_doc_ids=[doc_id],
        model="gpt-4o-mini",
        token_count=100,
    )

    hit = await semantic_cache.get(query)
    assert hit is not None, "Cache hit expected after put"
    assert hit.answer == "Old answer based on old content"

    invalidator = get_cache_invalidator()
    count = await invalidator.invalidate_doc(doc_id)
    assert count == 1, f"1 cached answer should be invalidated, got {count}"

    miss = await semantic_cache.get(query)
    assert miss is None, "Stale answer should not be served"

    after = get_cache_hit_counts()
    assert after["stale"] - before["stale"] >= 1, (
        "semantic_cache_hits_total{status=stale} must increment"
    )


async def test_no_stale_answers_served_on_100_doc_updates(semantic_cache):
    """100 cached answers + 100 doc updates: every answer invalidated, zero stale answers served.

    ADR-011 pilot criterion "stale answers <1%" is strict — served stale count must be 0.
    """
    invalidator = get_cache_invalidator()

    doc_ids = [uuid4() for _ in range(100)]
    queries = [f"Query about doc {doc_id}" for doc_id in doc_ids]
    for query, doc_id in zip(queries, doc_ids):
        await semantic_cache.put(query, f"answer_{query}", [doc_id], "gpt-4o-mini", 100)

    for doc_id in doc_ids:
        invalidated = await invalidator.invalidate_doc(doc_id)
        assert invalidated == 1, f"Each doc must invalidate exactly 1 answer, got {invalidated}"

    served_stale = 0
    not_invalidated = 0
    for query in queries:
        result = await semantic_cache.get(query)
        if result is not None:
            served_stale += 1
        else:
            not_invalidated += 1

    assert served_stale == 0, f"Stale rate {served_stale}% >= 1% — ADR-011 pilot FAIL"
    assert not_invalidated == 100, f"Only {not_invalidated}/100 answers were invalidated"


async def test_invalidation_latency_under_budget(semantic_cache):
    """Invalidate 100 cached answers within semantic_cache_invalidation_timeout_seconds budget."""
    invalidator = get_cache_invalidator()

    doc_ids = [uuid4() for _ in range(100)]
    for index, doc_id in enumerate(doc_ids):
        await semantic_cache.put(
            f"latency query {index} {doc_id}", f"a{index}", [doc_id], "gpt-4o-mini", 100
        )

    timeout = settings.semantic_cache_invalidation_timeout_seconds
    t0 = time.perf_counter()
    invalidated = await invalidator.invalidate_batch(doc_ids)
    elapsed = time.perf_counter() - t0

    assert invalidated == 100, (
        f"Batch invalidation should mark 100 answers stale, got {invalidated}"
    )
    assert elapsed < timeout, f"Invalidation of 100 docs took {elapsed:.1f}s > budget {timeout}s"
