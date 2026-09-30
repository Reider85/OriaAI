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
    from ...rag.pipeline import RagPipeline

    pipeline = RagPipeline.from_settings(settings)
    result = await pipeline.retrieve(query, top_k=top_k)
    logger.info(
        "rag_query query=%r top_k=%d returned=%d chunks",
        query,
        top_k,
        result.get("chunk_count", 0),
    )
    return result


rag_query = tool(rag_query, args_schema=RagQueryArgs)
