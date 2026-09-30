"""Hybrid indexing orchestration — BM25 + vector in parallel (ADR-020 / D-2)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .bm25_indexer import BM25IndexBuilder
from .models import Document

logger = logging.getLogger(__name__)

VectorIndexer = Callable[[Document], Awaitable[None]]


async def index_document_with_hybrid(
    document: Document,
    bm25_indexer: BM25IndexBuilder,
    vector_indexer: VectorIndexer | None = None,
) -> dict[str, Any]:
    """Index a document into BM25 and (optionally) the vector store in parallel.

    Failures are independent: if the vector leg fails the BM25 row is kept
    and a warning is logged, and vice versa. Only when *every* leg fails is
    the first exception raised.

    Returns:
        {"bm25_indexed": bool, "vector_indexed": bool | None}
    """
    tasks: list[Awaitable[Any]] = [bm25_indexer.index_document(document)]
    labels = ["bm25"]
    if vector_indexer is not None:
        tasks.append(vector_indexer(document))
        labels.append("vector")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    bm25_ok = not isinstance(results[0], BaseException)
    vector_ok: bool | None = None
    if vector_indexer is not None:
        vector_ok = not isinstance(results[1], BaseException)

    for label, result in zip(labels, results):
        if isinstance(result, BaseException):
            logger.warning(
                "Hybrid indexing leg %r failed for document %s: %s",
                label,
                document.id,
                result,
            )

    if not bm25_ok and vector_ok is not True:
        raise results[0]

    return {"bm25_indexed": bm25_ok, "vector_indexed": vector_ok}
