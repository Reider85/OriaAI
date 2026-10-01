import os
from collections.abc import Sequence

from llm_client.rag.rerankers.base import Reranker, RerankResult


class CohereRerankAdapter(Reranker):
    """Cohere Rerank API adapter for external reranking (optional alternative to BGE)."""
    
    def __init__(
        self,
        api_key: str | None = None,  # from env COHERE_API_KEY
        model: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self._client: object | None = None  # lazy, type depends on cohere version
        self._api_key = api_key or os.getenv("COHERE_API_KEY")
        self._model = model or os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")
        self._timeout = timeout_seconds or int(os.getenv("COHERE_TIMEOUT_SECONDS", "10"))

    @property
    def name(self) -> str:
        return "cohere-rerank"

    async def _ensure_client(self):
        if self._client is None:
            try:
                import cohere
                self._client = cohere.AsyncClient(self._api_key)
            except ImportError:
                raise ImportError("cohere package is required for CohereRerankAdapter. Install with: pip install 'llm-client[rerank]'")
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
        
        # Handle cohere v5/v6 vs v7 API differences
        try:
            # Try v7 API first
            response = await client.rerank(
                model=self._model,
                query=query,
                documents=docs_text,
                top_n=top_k,
                return_documents=False,
            )
            results = response.results
        except AttributeError:
            # Fallback to v5/v6 API
            response = await client.rerank(
                model=self._model,
                query=query,
                documents=docs_text,
                top_n=top_k,
                return_documents=False,
            )
            results = response.results
        
        return [
            RerankResult(
                doc_id=documents[r.index].get("id", str(r.index)),
                score=r.relevance_score,
                original_index=r.index,
            )
            for r in results
        ]

    async def health_check(self) -> bool:
        try:
            client = await self._ensure_client()
            # Cheap API call to check connectivity
            await client.models.list()
            return True
        except Exception:  # noqa: BLE001 — health probe must never raise
            # Catch any cohere-related errors (APIError, RateLimitError, UnauthorizedError, etc.)
            return False