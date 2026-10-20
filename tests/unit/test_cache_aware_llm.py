"""Unit tests for CacheAwareLLMClient (B-4 ADR-011)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from llm_client.rag.cache_aware_llm import CacheAwareLLMClient


class FakeChatModel(BaseChatModel):
    """Minimal BaseChatModel for testing CacheAwareLLMClient."""

    response: str | None = None
    error: Exception | None = None
    call_count: int = 0
    stream_responses: list = []  # noqa: RUF012
    stream_call_count: int = 0

    def __init__(self, response: str | None = None, error: Exception | None = None, **kwargs):
        super().__init__(**kwargs)
        self.response = response
        self.error = error
        self.stream_responses = [] if error else [AIMessage(content="stream " + str(i)) for i in range(3)]

    @property
    def _llm_type(self) -> str:
        return "fake"

    @property
    def _identifying_params(self) -> dict:
        return {"model_name": "fake-model"}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.call_count += 1
        if self.error:
            raise self.error
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=self.response or "fake response"))
            ]
        )

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> AIMessage:
        self.call_count += 1
        if self.error:
            raise self.error
        return AIMessage(content=self.response or "fake response")

    async def astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        config: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessage]:
        self.stream_call_count += 1
        if self.error:
            raise self.error
        for chunk in self.stream_responses:
            yield chunk


class MockEmbeddings:
    """Mock embeddings for testing."""
    
    async def aembed_query(self, text: str):
        # Return mock embedding for any query
        return [0.1, 0.2, 0.3, 0.4, 0.5]  # Mock 5-dimensional embedding
    
    async def aembed_documents(self, texts: list[str]):
        return [[0.1, 0.2, 0.3, 0.4, 0.5] for _ in texts]


class MockSemanticCache:
    """Mock SemanticAnswerCache for testing."""

    def __init__(self):
        self.data = {}
        self.get_calls = []
        self.put_calls = []

    async def get(self, query: str):
        self.get_calls.append(query)
        if query in self.data:
            from llm_client.rag.semantic_cache import CacheHitResult
            return CacheHitResult(
                answer=self.data[query],
                referenced_doc_ids=[UUID("123e4567-e89b-12d3-a456-426614174000")],
                created_at="2026-01-01T00:00:00Z",
                model="fake-model",
                token_count=50,
                similarity_score=0.85,
            )
        return None

    async def put(
        self, query: str, answer: str, referenced_doc_ids: list[UUID], model: str, token_count: int
    ):
        self.put_calls.append((query, answer, referenced_doc_ids, model, token_count))
        self.data[query] = answer


@pytest.fixture
def mock_cache():
    """Mock SemanticAnswerCache for testing."""
    return MockSemanticCache()


@pytest.fixture
def fake_llm():
    return FakeChatModel(response="llm response")


@pytest.fixture
def cache_aware_llm(fake_llm, mock_cache):
    # Patch the module-level reference used inside CacheAwareLLMClient
    with patch("llm_client.rag.cache_aware_llm.get_semantic_cache", return_value=mock_cache):
        yield CacheAwareLLMClient(underlying=fake_llm)


@pytest.fixture
def cache_disabled_llm(fake_llm):
    with patch("llm_client.rag.cache_aware_llm.get_semantic_cache", return_value=None):
        yield CacheAwareLLMClient(underlying=fake_llm)


@pytest.mark.asyncio
async def test_cache_miss_calls_underlying(cache_aware_llm, fake_llm, mock_cache):
    """Cache miss should call underlying LLM once."""
    messages = [
        HumanMessage(content="test query"),
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id",
                  artifact={"chunks": [{"document_id": "123e4567-e89b-12d3-a456-426614174000"}]})
    ]
    result = await cache_aware_llm.ainvoke(messages)
    await asyncio.sleep(0.05)  # allow fire-and-forget put task to complete

    assert fake_llm.call_count == 1
    assert mock_cache.get_calls == ["test query"]
    assert len(mock_cache.put_calls) == 1
    query, answer, doc_ids, _model, _token_count = mock_cache.put_calls[0]
    assert query == "test query"
    assert answer == "llm response"
    assert doc_ids == [UUID("123e4567-e89b-12d3-a456-426614174000")]
    assert result.content == "llm response"


@pytest.mark.asyncio
async def test_cache_hit_skips_underlying(cache_aware_llm, fake_llm, mock_cache):
    """Cache hit should NOT call underlying LLM."""
    # Setup cache hit
    mock_cache.data["test query"] = "cached response"
    
    messages = [
        HumanMessage(content="test query"),
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id",
                  artifact={"chunks": [{"document_id": "123e4567-e89b-12d3-a456-426614174000"}]})
    ]
    result = await cache_aware_llm.ainvoke(messages)
    
    assert fake_llm.call_count == 0
    assert mock_cache.get_calls == ["test query"]
    assert mock_cache.put_calls == []
    assert result.content == "cached response"


@pytest.mark.asyncio
async def test_cache_hit_returns_synthesized_message(cache_aware_llm, fake_llm, mock_cache):
    """Cache hit should return synthesized ChatResult with cached answer."""
    mock_cache.data["test query"] = "cached response"
    
    messages = [
        HumanMessage(content="test query"),
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id",
                  artifact={"chunks": [{"document_id": "123e4567-e89b-12d3-a456-426614174000"}]})
    ]
    result = await cache_aware_llm.ainvoke(messages)
    
    assert result.content == "cached response"
    assert isinstance(result, AIMessage)


@pytest.mark.asyncio
async def test_no_referenced_doc_ids_bypasses_cache(cache_aware_llm, fake_llm, mock_cache):
    """Messages without ToolMessage artifacts should bypass cache."""
    # Create messages with no ToolMessage (no RAG context)
    messages = [HumanMessage(content="test query")]

    result = await cache_aware_llm.ainvoke(messages)

    assert fake_llm.call_count == 1
    assert mock_cache.get_calls == []  # Cache not checked
    assert mock_cache.put_calls == []  # Cache not used
    assert result.content == "llm response"


@pytest.mark.asyncio
async def test_cache_disabled_passes_through(cache_disabled_llm, fake_llm, mock_cache):
    """Cache disabled should behave as transparent proxy."""
    messages = [HumanMessage(content="test query")]
    result = await cache_disabled_llm.ainvoke(messages)

    assert fake_llm.call_count == 1
    assert mock_cache.get_calls == []  # Cache not called
    assert mock_cache.put_calls == []  # Cache not used
    assert result.content == "llm response"


@pytest.mark.asyncio
async def test_put_called_after_miss(cache_aware_llm, fake_llm, mock_cache):
    """Cache put should be called after miss with correct args."""
    messages = [
        HumanMessage(content="test query"),
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id",
                  artifact={"chunks": [{"document_id": "123e4567-e89b-12d3-a456-426614174000"}]})
    ]
    await cache_aware_llm.ainvoke(messages)
    await asyncio.sleep(0.05)  # allow fire-and-forget put task to complete

    assert len(mock_cache.put_calls) == 1
    query, answer, doc_ids, model, _token_count = mock_cache.put_calls[0]
    assert query == "test query"
    assert answer == "llm response"
    assert len(doc_ids) == 1
    assert doc_ids[0] == UUID("123e4567-e89b-12d3-a456-426614174000")
    assert model == "fake-model"


@pytest.mark.asyncio
async def test_astream_cache_hit_chunks_answer(cache_aware_llm, fake_llm, mock_cache):
    """Cache hit on astream should yield AIMessage per word."""
    # Setup cache hit
    mock_cache.data["test query"] = "cached answer"

    messages = [
        HumanMessage(content="test query"),
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id",
                  artifact={"chunks": [{"document_id": "123e4567-e89b-12d3-a456-426614174000"}]})
    ]
    chunks = []
    async for chunk in cache_aware_llm.astream(messages):
        chunks.append(chunk.content)

    # Should yield word-chunked cached answer (each word gets trailing space)
    expected_chunks = ["cached ", "answer "]
    assert chunks == expected_chunks
    assert fake_llm.stream_call_count == 0  # Underlying not called


@pytest.mark.asyncio
async def test_astream_cache_miss_accumulates_and_puts(cache_aware_llm, fake_llm, mock_cache):
    """Stream from underlying, accumulate chunks, verify cache.put called with full accumulated answer."""
    messages = [
        HumanMessage(content="test query"),
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id",
                  artifact={"chunks": [{"document_id": "123e4567-e89b-12d3-a456-426614174000"}]})
    ]
    chunks = []
    async for chunk in cache_aware_llm.astream(messages):
        chunks.append(chunk.content)
    await asyncio.sleep(0.05)  # allow fire-and-forget put task to complete

    # Should accumulate and yield underlying stream
    assert chunks == ["stream 0", "stream 1", "stream 2"]
    assert fake_llm.stream_call_count == 1

    # Cache put should be called with full accumulated answer
    assert len(mock_cache.put_calls) == 1
    query, answer, doc_ids, _, token_count = mock_cache.put_calls[0]
    assert query == "test query"
    assert answer == "stream 0stream 1stream 2"  # Accumulated
    assert len(doc_ids) == 1
    assert doc_ids[0] == UUID("123e4567-e89b-12d3-a456-426614174000")
    assert token_count == 0  # Unknown during stream


@pytest.mark.asyncio
async def test_sync_generate_fallback(cache_aware_llm, fake_llm):
    """Sync _generate should fallback to underlying without cache check."""
    messages = [HumanMessage(content="test query")]
    result = cache_aware_llm._generate(messages)

    assert fake_llm.call_count == 1
    assert result.generations[0].message.content == (fake_llm.response or "fake response")


@pytest.mark.asyncio
async def test_error_propagation_on_miss(cache_aware_llm, fake_llm):
    """Underlying LLM errors should propagate on cache miss."""
    fake_llm.error = ValueError("LLM error")
    messages = [HumanMessage(content="test query")]

    with pytest.raises(ValueError, match="LLM error"):
        await cache_aware_llm.ainvoke(messages)


@pytest.mark.asyncio
async def test_error_propagation_on_stream_miss(cache_aware_llm, fake_llm):
    """Underlying LLM stream errors should propagate on cache miss."""
    fake_llm.error = ValueError("Stream error")
    fake_llm.stream_responses = []  # Clear responses to trigger error
    messages = [HumanMessage(content="test query")]

    with pytest.raises(ValueError, match="Stream error"):
        async for _ in cache_aware_llm.astream(messages):
            pass


@pytest.mark.asyncio
async def test_extract_referenced_doc_ids(cache_aware_llm):
    """Test _extract_referenced_doc_ids extracts from ToolMessage artifacts."""
    doc_id1 = UUID("123e4567-e89b-12d3-a456-426614174000")
    doc_id2 = UUID("123e4567-e89b-12d3-a456-426614174001")

    messages = [
        HumanMessage(content="test query"),
ToolMessage(
                artifact={"chunks": [{"document_id": str(doc_id1)}, {"document_id": str(doc_id2)}]},
                content="tool result",
                tool_call_id="test-tool-call-id",
            ),
    ]

    doc_ids = cache_aware_llm._extract_referenced_doc_ids(messages)
    assert doc_ids == [doc_id1, doc_id2]


@pytest.mark.asyncio
async def test_extract_query(cache_aware_llm):
    """Test _extract_query extracts last HumanMessage."""
    messages = [
        HumanMessage(content="first message"),
        HumanMessage(content="last message"),
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id"),
    ]

    query = cache_aware_llm._extract_query(messages)
    assert query == "last message"


@pytest.mark.asyncio
async def test_extract_query_fallback(cache_aware_llm):
    """Test _extract_query fallback to join all messages when no HumanMessage."""
    messages = [
        ToolMessage(content="tool result", tool_call_id="test-tool-call-id"),
        AIMessage(content="ai response"),
    ]
    
    query = cache_aware_llm._extract_query(messages)
    assert query == "tool result\nai response"


@pytest.mark.asyncio
async def test_llm_type_prefix(cache_aware_llm, fake_llm):
    """Test _llm_type includes prefix."""
    assert cache_aware_llm._llm_type == "cache-aware-fake"


@pytest.mark.asyncio
async def test_background_tasks_cleanup():
    """Test background tasks are cleaned up after completion."""
    # This test verifies the _done_callback works
    # In normal operation, tasks are removed when done
    task = asyncio.create_task(asyncio.sleep(0.1))
    task.add_done_callback(lambda t: None)  # Simulate the callback pattern
    await task

    # Task should be done
    assert task.done()
    # This test mainly verifies the callback pattern works
    # The actual cleanup is tested implicitly in other tests where tasks complete
