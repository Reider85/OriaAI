"""Unit tests for CacheInvalidator (B-3 ADR-011)."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from llm_client.rag.cache_invalidator import CacheInvalidator, get_cache_invalidator


class FakeSemanticCache:
    """Minimal mock for testing CacheInvalidator."""

    def __init__(self):
        self.mark_stale_calls = []
        self.mark_stale_results = {}

    async def mark_stale(self, doc_id):
        """Mock mark_stale with optional return value per test."""
        self.mark_stale_calls.append(doc_id)
        return self.mark_stale_results.get(doc_id, 0)


def test_get_cache_invalidator_singleton():
    """Test get_cache_invalidator returns same instance."""
    invalidator1 = get_cache_invalidator()
    invalidator2 = get_cache_invalidator()
    assert invalidator1 is invalidator2


@pytest.mark.asyncio
async def test_invalidate_doc_calls_mark_stale():
    """Test invalidate_doc calls cache.mark_stale with UUID."""
    fake_cache = FakeSemanticCache()

    # Use the same doc_id for both the key and the test
    doc_id = uuid4()
    fake_cache.mark_stale_results[doc_id] = 2  # Return 2 for this specific doc_id

    invalidator = CacheInvalidator()

    # Mock get_semantic_cache to return our fake cache
    with patch("llm_client.rag.cache_invalidator.get_semantic_cache", return_value=fake_cache):
        result = await invalidator.invalidate_doc(doc_id)

        assert fake_cache.mark_stale_calls == [doc_id]
        assert result == 2


@pytest.mark.asyncio
async def test_invalidate_doc_returns_zero_if_cache_disabled():
    """Test invalidate_doc returns 0 when semantic cache is disabled."""
    with patch("llm_client.rag.cache_invalidator.get_semantic_cache", return_value=None):
        invalidator = CacheInvalidator()
        doc_id = uuid4()
        result = await invalidator.invalidate_doc(doc_id)

        assert result == 0


@pytest.mark.asyncio
async def test_invalidate_batch():
    """Test invalidate_batch calls invalidate_doc for each doc."""
    invalidator = CacheInvalidator()

    doc1 = uuid4()
    doc2 = uuid4()
    doc3 = uuid4()

    # Mock individual invalidate_doc calls
    with patch.object(
        invalidator,
        "invalidate_doc",
        side_effect=[
            1,  # doc1
            2,  # doc2
            3,  # doc3
        ],
    ) as mock_invalidate:
        result = await invalidator.invalidate_batch([doc1, doc2, doc3])

        assert result == 6  # 1 + 2 + 3
        assert mock_invalidate.call_count == 3


@pytest.mark.asyncio
async def test_invalidate_batch_empty():
    """Test invalidate_batch with empty list."""
    invalidator = CacheInvalidator()
    result = await invalidator.invalidate_batch([])
    assert result == 0


@pytest.mark.asyncio
async def test_invalidate_batch_with_disabled_cache():
    """Test invalidate_batch handles disabled cache gracefully."""
    with patch("llm_client.rag.cache_invalidator.get_semantic_cache", return_value=None):
        invalidator = CacheInvalidator()
        doc1 = uuid4()
        doc2 = uuid4()

        result = await invalidator.invalidate_batch([doc1, doc2])

        assert result == 0


@pytest.mark.asyncio
async def test_invalidate_doc_logs_when_cache_disabled():
    """Test that appropriate debug log is written when cache is disabled."""
    with (
        patch("llm_client.rag.cache_invalidator.logger") as mock_logger,
        patch("llm_client.rag.cache_invalidator.get_semantic_cache", return_value=None),
    ):
        invalidator = CacheInvalidator()
        doc_id = uuid4()

        await invalidator.invalidate_doc(doc_id)

        mock_logger.debug.assert_called_once_with("Semantic cache disabled — skip invalidation")
