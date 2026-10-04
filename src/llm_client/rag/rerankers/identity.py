from collections.abc import Sequence

from llm_client.rag.rerankers.base import Reranker, RerankResult


class IdentityReranker(Reranker):
    """No-op reranker for tests and development (returns documents unchanged)."""

    @property
    def name(self) -> str:
        return "identity"

    async def rerank(
        self,
        query: str,
        documents: Sequence[dict],
        top_k: int = 5,
        batch_size: int = 8,
    ) -> list[RerankResult]:
        """Returns first top_k documents without reranking."""
        return [
            RerankResult(
                doc_id=doc.get("id", str(i)),
                score=1.0,
                original_index=i,
            )
            for i, doc in enumerate(documents[:top_k])
        ]

    async def health_check(self) -> bool:
        """Always returns True for identity reranker."""
        return True
