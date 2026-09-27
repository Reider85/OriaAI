"""Reranker chain with graceful fallback for robust reranking."""

import logging
from collections.abc import Sequence

from llm_client.rag.rerankers.base import Reranker, RerankResult

logger = logging.getLogger(__name__)


class RerankerChain(Reranker):
    """Chain of rerankers with graceful fallback behavior.

    Tries rerankers in order, falling back to the next if one fails.
    If all rerankers fail, returns top-k documents without reranking.

    Args:
        rerankers: Ordered list of rerankers to try (primary, fallback1, fallback2)
    """

    def __init__(self, rerankers: Sequence[Reranker]):
        self._rerankers = rerankers  # ordered: primary, fallback1, fallback2

    @property
    def name(self) -> str:
        return "chain"

    async def rerank(
        self,
        query: str,
        documents: Sequence[dict],
        top_k: int = 5,
        batch_size: int | None = None,
    ) -> list[RerankResult]:
        """Try rerankers in sequence, fall back on failure.

        Args:
            query: The search query
            documents: Documents to rerank
            top_k: Number of top documents to return
            batch_size: Batch size for reranking (optional)

        Returns:
            Top-k reranked documents as RerankResult list

        Note:
            If all rerankers fail, returns first top_k documents with score=1.0
            (identity fallback behavior).
        """
        errors = []

        for reranker in self._rerankers:
            try:
                # Check health before attempting reranking
                if not await reranker.health_check():
                    errors.append(f"{reranker.name}: unhealthy")
                    continue

                # Attempt reranking
                results = await reranker.rerank(query, documents, top_k, batch_size or 8)

                # Log fallback if we had to skip primary rerankers
                if errors:
                    logger.warning(
                        "Reranker fallback occurred",
                        extra={
                            "primary": self._rerankers[0].name,
                            "active": reranker.name,
                            "errors": errors,
                        },
                    )

                return results

            except Exception as e:
                errors.append(f"{reranker.name}: {e!s}")
                continue

        # All rerankers failed - return identity fallback
        logger.error("All rerankers failed, using identity fallback", extra={"errors": errors})
        return [
            RerankResult(doc_id=str(i), score=1.0, original_index=i)
            for i, doc in enumerate(documents[:top_k])
        ]

    async def health_check(self) -> bool:
        """Healthy if at least one reranker in the chain is healthy.

        Returns:
            True if any reranker is ready to serve, False otherwise
        """
        for r in self._rerankers:
            if await r.health_check():
                return True
        return False
