"""Integration tests for B-5 Pipeline integration: end-to-end graph + semantic cache."""

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from llm_client.agent.graph import build_agent_graph
from llm_client.rag.semantic_cache import SemanticAnswerCache


class MockOpenAIEmbeddings:
    """Mock OpenAIEmbeddings for integration tests."""

    def __init__(self):
        self.vector_db = {
            "what is python": [0.1, 0.2, 0.3] * 512,
            "what is the python language": [0.71, 0.81, 0.91] * 512,
        }

    async def aembed_query(self, query: str) -> list[float]:
        return self.vector_db.get(query, [0.0] * 1536)


@pytest.fixture
async def real_semantic_cache():
    """Fixture providing real SemanticAnswerCache with mock embeddings."""
    mock_embeddings = MockOpenAIEmbeddings()
    
    # Use in-memory Redis-like client for testing
    try:
        import redis.asyncio as aioredis

        from llm_client.config import settings
        
        # Try to connect to Redis DB 2
        client = aioredis.from_url(settings.redis_semantic_cache_url, decode_responses=False)
        await client.ping()
        yield SemanticAnswerCache(
            redis_client=client,
            embeddings=mock_embeddings,
            ttl_seconds=86400,
            similarity_threshold=0.92,
            max_entries=10000,
        )
        await client.aclose()
    except Exception:  # noqa: BLE001
        # Skip if Redis not available
        pytest.skip("Redis not available for semantic cache integration test")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_graph_semantic_cache_miss_then_hit(fake_llm, real_semantic_cache):
    """Test end-to-end semantic cache with real Redis - miss then hit scenario."""
    # Mock the underlying LLM
    fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Python is a high-level programming language"))
    
    # Build graph with real semantic cache
    graph = build_agent_graph(
        fake_llm, 
        use_semantic_cache=True,
        tools=[]
    )
    
    # First run: MISS
    state1 = {
        "messages": [
            HumanMessage(content="What is Python?"),
            ToolMessage(
                content=json.dumps({
                    "chunks": [{
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "content": "Python is a programming language",
                        "metadata": {
                            "document_id": "123e4567-e89b-12d3-a456-426614174000"
                        }
                    }]
                }),
                tool_call_id="123",
                name="rag_query"
            )
        ],
        "iteration": 0,
        "max_iterations": 10,
    }
    
    # Run first graph execution
    result1 = {}
    async for chunk in graph.astream(state1):
        result1.update(chunk)
    
    # Verify first result
    assert "final_answer" in result1
    assert result1["final_answer"]["final_answer"] == "Python is a high-level programming language"
    
    # Verify underlying LLM was called in first run
    fake_llm.ainvoke.assert_called_once()
    
    # Second run: HIT (with fresh graph to simulate new session)
    fake_llm.ainvoke.reset_mock()
    graph2 = build_agent_graph(
        fake_llm, 
        use_semantic_cache=True,
        tools=[]
    )
    
    state2 = {
        "messages": [
            HumanMessage(content="What is Python?"),
            ToolMessage(
                content=json.dumps({
                    "chunks": [{
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "content": "Python is a programming language",
                        "metadata": {
                            "document_id": "123e4567-e89b-12d3-a456-426614174000"
                        }
                    }]
                }),
                tool_call_id="456",  # Different tool call ID
                name="rag_query"
            )
        ],
        "iteration": 0,
        "max_iterations": 10,
    }
    
    # Run second graph execution
    result2 = {}
    async for chunk in graph2.astream(state2):
        result2.update(chunk)
    
    # Verify second result
    assert "final_answer" in result2
    assert result2["final_answer"]["final_answer"] == "Python is a high-level programming language"
    
    # Verify underlying LLM was NOT called in second run (cache hit)
    fake_llm.ainvoke.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_semantic_cache_with_tools():
    """Test semantic cache integration with tools."""
    fake_llm = FakeListChatModel(responses=["I'll help you with that task"])
    
    # Mock the underlying LLM to return tool calls
    fake_llm.ainvoke = AsyncMock(return_value=AIMessage(
        content="",
        tool_calls=[{"name": "file_export", "args": {"content": "test"}, "id": "123"}]
    ))
    
    # Mock tool execution
    mock_tool = AsyncMock(return_value="Export completed")
    
    # Build graph with semantic cache and tools
    graph = build_agent_graph(
        fake_llm, 
        tools=[mock_tool],
        use_semantic_cache=True
    )
    
    state = {
        "messages": [
            HumanMessage(content="Export this file"),
            ToolMessage(
                content=json.dumps({
                    "chunks": [{
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "content": "File content to export",
                        "metadata": {
                            "document_id": "123e4567-e89b-12d3-a456-426614174000"
                        }
                    }]
                }),
                tool_call_id="rag_123",
                name="rag_query"
            )
        ],
        "iteration": 0,
        "max_iterations": 10,
    }
    
    # Run the graph
    result = {}
    async for chunk in graph.astream(state):
        result.update(chunk)
    
    # Verify tool was executed
    assert mock_tool.called
    
    # Verify final answer contains tool result
    assert "final_answer" in result
    assert "Export completed" in result["final_answer"]["final_answer"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_semantic_cache_bypass_without_documents():
    """Test that cache is bypassed when no document references."""
    fake_llm = FakeListChatModel(responses=["The weather is sunny"])
    
    # Track LLM calls
    fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content="The weather is sunny"))
    
    # Build graph with semantic cache
    graph = build_agent_graph(
        fake_llm, 
        use_semantic_cache=True
    )
    
    state = {
        "messages": [HumanMessage(content="What is the weather?")],
        "iteration": 0,
        "max_iterations": 10,
    }
    
    # Run the graph
    result = {}
    async for chunk in graph.astream(state):
        result.update(chunk)
    
    # Verify final answer
    assert "final_answer" in result
    assert result["final_answer"]["final_answer"] == "The weather is sunny"
    
    # Verify LLM was called (cache bypassed due to no document references)
    fake_llm.ainvoke.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_semantic_cache_multiple_queries():
    """Test semantic cache with multiple different queries."""
    fake_llm = FakeListChatModel(responses=[
        "Python is a programming language",
        "Java is a programming language",
        "JavaScript is a programming language"
    ])
    
    # Track LLM calls
    fake_llm.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(content="Python is a programming language"),
            AIMessage(content="Java is a programming language"),
            AIMessage(content="JavaScript is a programming language")
        ]
    )
    
    # Build graph with semantic cache
    graph = build_agent_graph(
        fake_llm, 
        use_semantic_cache=True
    )
    
    # First query: Python
    state1 = {
        "messages": [
            HumanMessage(content="What is Python?"),
            ToolMessage(
                content=json.dumps({
                    "chunks": [{
                        "id": "python-doc",
                        "content": "Python documentation",
                        "metadata": {"document_id": "python-doc"}
                    }]
                }),
                tool_call_id="rag_1",
                name="rag_query"
            )
        ],
        "iteration": 0,
        "max_iterations": 10,
    }
    
    # Run first query
    result1 = {}
    async for chunk in graph.astream(state1):
        result1.update(chunk)
    
    # Second query: Java (different, should call LLM)
    state2 = {
        "messages": [
            HumanMessage(content="What is Java?"),
            ToolMessage(
                content=json.dumps({
                    "chunks": [{
                        "id": "java-doc",
                        "content": "Java documentation",
                        "metadata": {"document_id": "java-doc"}
                    }]
                }),
                tool_call_id="rag_2",
                name="rag_query"
            )
        ],
        "iteration": 0,
        "max_iterations": 10,
    }
    
    # Run second query
    result2 = {}
    async for chunk in graph.astream(state2):
        result2.update(chunk)
    
    # Verify both results
    assert result1["final_answer"]["final_answer"] == "Python is a programming language"
    assert result2["final_answer"]["final_answer"] == "Java is a programming language"
    
    # Verify LLM was called twice (both queries different)
    assert fake_llm.ainvoke.call_count == 2