"""Unit tests for index_document_with_hybrid (ADR-020 / D-2)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_client.rag.indexing.hybrid_indexer import index_document_with_hybrid
from llm_client.rag.indexing.models import Document


def _doc() -> Document:
    return Document(
        id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        source_type="file",
        content_hash="hash-1",
        content="hello",
        meta={},
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


@pytest.mark.asyncio
async def test_facts_extractor_succeeds():
    """Test that facts extraction succeeds and doesn't affect return value."""
    bm25 = MagicMock()
    bm25.index_document = AsyncMock(return_value=None)
    vector = AsyncMock(return_value=None)

    facts_extractor = AsyncMock()
    facts_extractor.extract_from_document = AsyncMock(return_value=None)

    test_doc = _doc()
    result = await index_document_with_hybrid(test_doc, bm25, vector, facts_extractor)

    assert result == {"bm25_indexed": True, "vector_indexed": True}
    bm25.index_document.assert_awaited_once()
    vector.assert_awaited_once()
    facts_extractor.extract_from_document.assert_awaited_once_with(test_doc)


@pytest.mark.asyncio
async def test_facts_extractor_failure_is_tolerated():
    """Test that facts extraction failure is logged but doesn't raise."""
    bm25 = MagicMock()
    bm25.index_document = AsyncMock(return_value=None)
    vector = AsyncMock(return_value=None)

    facts_extractor = AsyncMock()
    facts_extractor.extract_from_document = AsyncMock(
        side_effect=RuntimeError("facts extraction failed")
    )

    test_doc = _doc()
    result = await index_document_with_hybrid(test_doc, bm25, vector, facts_extractor)

    assert result == {"bm25_indexed": True, "vector_indexed": True}
    bm25.index_document.assert_awaited_once()
    vector.assert_awaited_once()
    facts_extractor.extract_from_document.assert_awaited_once_with(test_doc)
