"""rag_query tool + rag_retriever node (AG-6, Phase 2).

Implements ADR-003 (VectorStoreFactory) on a concrete retrieval
pipeline. Extended by ADR-017 (reranker, Block C) and ADR-020
(hybrid retrieval, Block D) in the same Phase 2.
"""

import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RagQueryArgs(BaseModel):
    query: str = Field(..., description="Поисковый запрос по корпусу документов")
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of chunks to return after reranker (1-20)",
    )


async def rag_query(query: str, top_k: int = 5) -> dict[str, Any]:
    """Ищет по корпоративному корпусу документов. Возвращает dict
    {chunks: [{source_uri, title, page, content_preview, score}],
    chunk_count, top_score, source_uris}.

    Pipeline: vector retrieval (top-20) → [BM25 retrieval (top-20) →
    RRF fusion (top-50)] (if strategy=hybrid, ADR-020) → reranker
    top-5 (ADR-017). PII filtering applied (ADR-014 metadata).
    """
    from ...config import settings
    from ...rag.pipeline_singleton import get_pipeline_for_request, get_rag_request_overrides

    try:
        # Get request-level UI overrides from contextvar
        request_overrides = get_rag_request_overrides()
        pipeline = await get_pipeline_for_request(settings, request_overrides)
        if pipeline is None:
            logger.warning("RAG pipeline not available - returning empty results")
            return {"chunks": [], "chunk_count": 0, "top_score": 0.0, "source_uris": []}

        result = await pipeline.retrieve(query, top_k=top_k)
        logger.info(
            "rag_query query=%r top_k=%d returned=%d chunks",
            query,
            top_k,
            result.get("chunk_count", 0),
        )
        return result
    except (ImportError, ValueError, RuntimeError) as exc:
        logger.error("rag_query failed: %s", exc)
        return {"chunks": [], "chunk_count": 0, "top_score": 0.0, "source_uris": []}


rag_query = tool(rag_query, args_schema=RagQueryArgs)  # type: ignore[assignment]
