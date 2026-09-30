"""Unit tests for index_document_with_hybrid (ADR-020 / D-2)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_client.rag.indexing.hybrid_indexer import index_document_with_hybrid
from llm_client.rag.indexing.models import Document


def _doc() -> Document:
    return Document(
        id="doc-1",
        user_id="user-1",
        source_type="file",
        content_hash="hash-1",
        content="hello",
    )


@pytest.mark.asyncio
async def test_both_legs_succeed():
    bm25 = MagicMock()
    bm25.index_document = AsyncMock(return_value=None)
    vector = AsyncMock(return_value=None)

    result = await index_document_with_hybrid(_doc(), bm25, vector)

    assert result == {"bm25_indexed": True, "vector_indexed": True}
    bm25.index_document.assert_awaited_once()
    vector.assert_awaited_once()


@pytest.mark.asyncio
async def test_vector_failure_keeps_bm25():
    bm25 = MagicMock()
    bm25.index_document = AsyncMock(return_value=None)

    async def failing_vector(doc):
        raise RuntimeError("vector down")

    result = await index_document_with_hybrid(_doc(), bm25, failing_vector)

    assert result == {"bm25_indexed": True, "vector_indexed": False}
    bm25.index_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_bm25_failure_keeps_vector():
    async def failing_bm25(doc):
        raise RuntimeError("bm25 down")

    bm25 = MagicMock()
    bm25.index_document = failing_bm25
    vector = AsyncMock(return_value=None)

    result = await index_document_with_hybrid(_doc(), bm25, vector)

    assert result == {"bm25_indexed": False, "vector_indexed": True}
    vector.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_failures_raise_first_exception():
    async def failing_bm25(doc):
        raise RuntimeError("bm25 down")

    async def failing_vector(doc):
        raise RuntimeError("vector down")

    bm25 = MagicMock()
    bm25.index_document = failing_bm25

    with pytest.raises(RuntimeError, match="bm25 down"):
        await index_document_with_hybrid(_doc(), bm25, failing_vector)


@pytest.mark.asyncio
async def test_vector_disabled_is_bm25_only():
    bm25 = MagicMock()
    bm25.index_document = AsyncMock(return_value=None)

    result = await index_document_with_hybrid(_doc(), bm25, None)

    assert result == {"bm25_indexed": True, "vector_indexed": None}
    bm25.index_document.assert_awaited_once()
