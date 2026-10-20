"""Cache invalidator for ADR-011 Tier-3 semantic cache.

When a document is updated or deleted, mark all cached LLM answers
referencing that document as stale. Stale answers are not served
(SemanticAnswerCache.get returns None for stale entries).

Architecture: ARCHITECT.md v1.3.0 §5.2.5.
TRIZ: principle #9 (preliminary action — preemptive invalidation
before stale answer is served).
"""
import logging
from uuid import UUID

from .semantic_cache import get_semantic_cache

logger = logging.getLogger(__name__)


class CacheInvalidator:
    """Wraps SemanticAnswerCache.mark_stale with metrics + logging."""

    async def invalidate_doc(self, doc_id: UUID) -> int:
        """Invalidate all cached answers referencing doc_id.
        Returns count of invalidated entries."""
        cache = get_semantic_cache()
        if cache is None:
            logger.debug("Semantic cache disabled — skip invalidation")
            return 0
        count = await cache.mark_stale(doc_id)
        if count > 0:
            logger.info(
                "Invalidated %d cached answers for doc_id=%s",
                count, doc_id,
            )
        return count

    async def invalidate_batch(self, doc_ids: list[UUID]) -> int:
        """Invalidate multiple docs at once. Returns total count."""
        total = 0
        for doc_id in doc_ids:
            total += await self.invalidate_doc(doc_id)
        return total


_singleton: CacheInvalidator | None = None


def get_cache_invalidator() -> CacheInvalidator:
    global _singleton
    if _singleton is None:
        _singleton = CacheInvalidator()
    return _singleton