import asyncio
import os
from collections.abc import Sequence

from sentence_transformers import CrossEncoder

from llm_client.rag.rerankers.base import Reranker, RerankResult


class BgeRerankerAdapter(Reranker):
    """In-process reranker using BGE-reranker-base model via CrossEncoder."""
    
    def __init__(
        self,
        model_name: str | None = None,
        model_dir: str | None = None,
        device: str | None = None,
        max_length: int | None = None,
        batch_size: int | None = None,
    ):
        self._model: CrossEncoder | None = None  # lazy load
        self._model_name = model_name or os.getenv("RERANKER_MODEL_NAME", "BAAI/bge-reranker-base")
        self._model_dir = model_dir or os.getenv("RERANKER_MODEL_DIR", "./models/bge-reranker-base")
        self._device = device or os.getenv("RERANKER_DEVICE", "cpu")
        self._max_length = max_length or int(os.getenv("RERANKER_MAX_LENGTH", "512"))
        self._batch_size = batch_size or int(os.getenv("RERANKER_BATCH_SIZE", "8"))

    @property
    def name(self) -> str:
        return "bge-reranker-base"

    async def _ensure_loaded(self):
        """Load the CrossEncoder model if not already loaded."""
        if self._model is None:
            # Load in thread to avoid blocking event loop
            self._model = await asyncio.to_thread(
                CrossEncoder,
                self._model_dir if os.path.exists(self._model_dir)
                  else self._model_name,
                device=self._device,
                max_length=self._max_length,
            )
        return self._model

    async def rerank(
        self,
        query: str,
        documents: Sequence[dict],
        top_k: int = 5,
        batch_size: int | None = None,
    ) -> list[RerankResult]:
        """Return top_k documents ranked by relevance to query using BGE reranker."""
        model = await self._ensure_loaded()
        bs = batch_size or self._batch_size
        
        # Build (query, doc_content) pairs
        pairs = [
            (query, doc["content"][:self._max_length]) 
            for doc in documents
        ]
        
        # Predict in thread (sync operation)
        scores = await asyncio.to_thread(
            model.predict, pairs, batch_size=bs
        )
        
        # Sort by score descending
        indexed = [(i, float(s)) for i, s in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        
        return [
            RerankResult(
                doc_id=documents[i].get("id", str(i)),
                score=s,
                original_index=i,
            )
            for i, s in indexed[:top_k]
        ]

    async def health_check(self) -> bool:
        """Check if the reranker model is loaded and ready."""
        try:
            await self._ensure_loaded()
            return True
        except (RuntimeError, OSError, ValueError):
            return False