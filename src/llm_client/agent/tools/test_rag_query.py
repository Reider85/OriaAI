"""Tests for AG-6 rag_query tool (H-2, Phase 2)."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from llm_client.agent.tools.rag_query import RagQueryArgs, rag_query

# ── RagQueryArgs schema tests ─────────────────────────────────────────────────


def test_rag_query_args_defaults():
    args = RagQueryArgs(query="test query")
    assert args.query == "test query"
    assert args.top_k == 5


def test_rag_query_args_custom_top_k():
    args = RagQueryArgs(query="test", top_k=10)
    assert args.top_k == 10


def test_rag_query_args_top_k_bounds():
    with pytest.raises(ValidationError):
        RagQueryArgs(query="test", top_k=0)
    with pytest.raises(ValidationError):
        RagQueryArgs(query="test", top_k=21)


# ── rag_query tool tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rag_query_returns_chunks():
    mock_result = {
        "chunks": [
            {
                "source_uri": "doc1",
                "title": "T1",
                "page": 1,
                "content_preview": "preview",
                "score": 0.9,
            },
            {
                "source_uri": "doc2",
                "title": "T2",
                "page": 2,
                "content_preview": "preview2",
                "score": 0.8,
            },
            {
                "source_uri": "doc3",
                "title": "T3",
                "page": 3,
                "content_preview": "preview3",
                "score": 0.7,
            },
        ],
        "chunk_count": 3,
        "top_score": 0.9,
        "source_uris": ["doc1", "doc2", "doc3"],
    }
    with patch("llm_client.rag.pipeline.RagPipeline") as MockPipeline:
        instance = MockPipeline.from_settings.return_value
        instance.retrieve = AsyncMock(return_value=mock_result)

        result = await rag_query.ainvoke({"query": "asyncio documentation", "top_k": 5})

        assert result["chunk_count"] == 3
        assert result["top_score"] == 0.9
        assert len(result["chunks"]) == 3
        assert result["source_uris"] == ["doc1", "doc2", "doc3"]
        instance.retrieve.assert_awaited_once_with("asyncio documentation", top_k=5)


@pytest.mark.asyncio
async def test_rag_query_top_k_param():
    with patch("llm_client.rag.pipeline.RagPipeline") as MockPipeline:
        instance = MockPipeline.from_settings.return_value
        instance.retrieve = AsyncMock(
            return_value={
                "chunks": [],
                "chunk_count": 0,
                "top_score": 0.0,
                "source_uris": [],
            }
        )

        await rag_query.ainvoke({"query": "test", "top_k": 3})

        instance.retrieve.assert_awaited_once_with("test", top_k=3)


@pytest.mark.asyncio
async def test_rag_query_default_top_k():
    with patch("llm_client.rag.pipeline.RagPipeline") as MockPipeline:
        instance = MockPipeline.from_settings.return_value
        instance.retrieve = AsyncMock(
            return_value={
                "chunks": [],
                "chunk_count": 0,
                "top_score": 0.0,
                "source_uris": [],
            }
        )

        await rag_query.ainvoke({"query": "test"})

        instance.retrieve.assert_awaited_once_with("test", top_k=5)


@pytest.mark.asyncio
async def test_rag_query_empty_results():
    with patch("llm_client.rag.pipeline.RagPipeline") as MockPipeline:
        instance = MockPipeline.from_settings.return_value
        instance.retrieve = AsyncMock(
            return_value={
                "chunks": [],
                "chunk_count": 0,
                "top_score": 0.0,
                "source_uris": [],
            }
        )

        result = await rag_query.ainvoke({"query": "nonexistent"})

        assert result["chunks"] == []
        assert result["chunk_count"] == 0
        assert result["top_score"] == 0.0
        assert result["source_uris"] == []


@pytest.mark.asyncio
async def test_rag_query_content_truncation():
    long_content = "x" * 1000
    mock_result = {
        "chunks": [
            {
                "source_uri": "",
                "title": "",
                "page": None,
                "content_preview": long_content[:200] + "...",
                "score": 0.5,
            },
        ],
        "chunk_count": 1,
        "top_score": 0.5,
        "source_uris": [],
    }
    with patch("llm_client.rag.pipeline.RagPipeline") as MockPipeline:
        instance = MockPipeline.from_settings.return_value
        instance.retrieve = AsyncMock(return_value=mock_result)

        result = await rag_query.ainvoke({"query": "test"})

        preview = result["chunks"][0]["content_preview"]
        assert len(preview) <= 204  # 200 chars + "..."
        assert preview.endswith("...")


@pytest.mark.asyncio
async def test_rag_query_tool_has_correct_name():
    assert rag_query.name == "rag_query"


@pytest.mark.asyncio
async def test_rag_query_tool_has_args_schema():
    assert rag_query.args_schema is RagQueryArgs
