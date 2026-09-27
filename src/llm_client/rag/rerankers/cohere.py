import os
from collections.abc import Sequence

import cohere

from llm_client.rag.rerankers.base import Reranker, RerankResult


class CohereRerankAdapter(Reranker):
    """Cohere Rerank API adapter for external reranking (optional alternative to BGE)."""
    
    def __init__(
        self,
        api_key: str | None = None,  # from env COHERE_API_KEY
        model: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self._client: cohere.AsyncClient | None = None  # lazy
        self._api_key = api_key or os.getenv("COHERE_API_KEY")
        self._model = model or os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")
        self._timeout = timeout_seconds or int(os.getenv("COHERE_TIMEOUT_SECONDS", "10"))

    @property
    def name(self) -> str:
        return "cohere-rerank"

    async def _ensure_client(self):
        if self._client is None:
            self._client = cohere.AsyncClient(self._api_key)
        return self._client

    async def rerank(
        self,
        query: str,
        documents: Sequence[dict],
        top_k: int = 5,
        batch_size: int | None = None,  # ignored, Cohere API handles batching
    ) -> list[RerankResult]:
        client = await self._ensure_client()
        docs_text = [doc["content"][:5000] for doc in documents]
        response = await client.rerank(
            model=self._model,
            query=query,
            documents=docs_text,
            top_n=top_k,
            return_documents=False,
        )
        return [
            RerankResult(
                doc_id=documents[r.index].get("id", str(r.index)),
                score=r.relevance_score,
                original_index=r.index,
            )
            for r in response.results
        ]

    async def health_check(self) -> bool:
        try:
            client = await self._ensure_client()
            # Cheap API call to check connectivity
            await client.models.list()
            return True
        except (cohere.APIError, cohere.RateLimitError, cohere.UnauthorizedError):
            return False