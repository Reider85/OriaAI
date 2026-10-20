"""Integration tests for CacheAwareLLMClient with real Redis."""

from typing import Any
from unittest.mock import patch

import pytest

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from llm_client.rag.cache_aware_llm import CacheAwareLLMClient


class MockOpenAIEmbeddings:
    """Mock OpenAIEmbeddings for integration tests."""

    def __init__(self):
        self.vector_db = {
            "what is python": [0.1, 0.2, 0.3] * 512,
            "what is the python language": [0.71, 0.81, 0.91] * 512,
        }

    async def aembed_query(self, query: str) -> list[float]:
        return self.vector_db.get(query, [0.0] * 1536)


class FakeChatModel(BaseChatModel):
    """Fake LLM model for integration tests."""

    def __init__(self, response: str = "Python is a high-level programming language."):
        super().__init__()
        self.response = response
        self.call_count = 0

    @property
    def _llm_type(self) -> str:
        return "fake"

    @property
    def _identifying_params(self) -> dict:
        return {"model_name": "gpt-4o-mini"}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.response))])

    async def _acall(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.call_count += 1
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.response))],
            llm_output={"token_usage": {"total_tokens": 100}},
        )

    async def astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        config: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[BaseMessage]:
        for word in self.response.split():
            yield AIMessage(content=word + " ")


@pytest.fixture
async def redis_client():
    """Fixture providing real Redis client for DB 2."""
    import redis.asyncio as aioredis

    # Use the same URL as configured in the application
    redis_url = "redis://127.0.0.1:6380/2"  # DB 2 for semantic cache

    client = aioredis.from_url(redis_url, decode_responses=False)
    try:
        # Test connection
        await client.ping()
        yield client
    except ConnectionError as e:
        pytest.skip(f"Redis not available on 6380/2: {e}")
    finally:
        await client.aclose()


@pytest.fixture
def mock_embeddings():
    """Fixture providing mock embeddings."""
    return MockOpenAIEmbeddings()


@pytest.fixture
def fake_llm():
    """Fixture providing fake LLM."""
    return FakeChatModel()


@pytest.fixture
def semantic_cache(redis_client, mock_embeddings):
    """Fixture providing real SemanticAnswerCache with real Redis and mock embeddings."""
    from llm_client.rag.semantic_cache import SemanticAnswerCache

    return SemanticAnswerCache(
        redis_client=redis_client,
        embeddings=mock_embeddings,
        ttl_seconds=86400,
        similarity_threshold=0.92,
        max_entries=10000,
    )


@pytest.fixture
def cache_aware_llm(fake_llm, semantic_cache):
    """Fixture providing CacheAwareLLMClient with real cache."""
    with patch("llm_client.rag.cache_aware_llm.get_semantic_cache", return_value=semantic_cache):
        return CacheAwareLLMClient(underlying=fake_llm)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_semantic_cache_hit(cache_aware_llm, fake_llm, semantic_cache):
    """Test end-to-end semantic cache with real Redis - hit scenario."""
    doc_id = "123e4567-e89b-12d3-a456-426614174000"
    query = "what is python"

    # First call: miss -> should call underlying LLM and cache the result
    messages = [
        HumanMessage(content=query),
        ToolMessage(artifact={"chunks": [{"document_id": doc_id}]}, content="tool result"),
    ]

    result = await cache_aware_llm._acall(messages)
    assert fake_llm.call_count == 1
    assert result.generations[0].message.content == "Python is a high-level programming language."

    # Verify cache was populated
    cached_result = await semantic_cache.get(query)
    assert cached_result is not None
    assert cached_result.answer == "Python is a high-level programming language."
    assert cached_result.referenced_doc_ids == [doc_id]

    # Second call: hit -> should NOT call underlying LLM, return cached result
    fake_llm.call_count = 0  # Reset counter
    result2 = await cache_aware_llm._acall(messages)

    assert fake_llm.call_count == 0  # Underlying not called
    assert result2.generations[0].message.content == "Python is a high-level programming language."

    # Verify cache hit metrics (recorded by SemanticAnswerCache internally)
    # This test mainly verifies the end-to-end flow; metrics are tested in unit tests


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_astream_cache_hit(cache_aware_llm, fake_llm, semantic_cache):
    """Test end-to-end astream with semantic cache hit."""
    doc_id = "123e4567-e89b-12d3-a456-426614174001"
    query = "what is the python language"

    # First call: miss -> should stream from underlying and cache
    messages = [
        HumanMessage(content=query),
        ToolMessage(artifact={"chunks": [{"document_id": doc_id}]}, content="tool result"),
    ]

    chunks = []
    async for chunk in cache_aware_llm.astream(messages):
        chunks.append(chunk.content)

    # Should have streamed from underlying
    assert len(chunks) > 0
    assert fake_llm.call_count == 1

    # Verify cache was populated
    cached_result = await semantic_cache.get(query)
    assert cached_result is not None
    assert cached_result.answer == "Python is a high-level programming language."

    # Second call: hit -> should NOT call underlying, return word-chunked cached answer
    fake_llm.call_count = 0
    chunks2 = []
    async for chunk in cache_aware_llm.astream(messages):
        chunks2.append(chunk.content)

    assert fake_llm.call_count == 0  # Underlying not called
    # Should be word-chunked from cached answer
    assert len(chunks2) > 0
    assert "".join(chunks2) == "Python is a high-level programming language."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_referenced_doc_ids_bypasses_cache_integration(
    cache_aware_llm, fake_llm, semantic_cache
):
    """Test that messages without ToolMessage artifacts bypass cache integration."""
    query = "what is python"

    # Messages without ToolMessage artifacts (no RAG context)
    messages = [HumanMessage(content=query)]

    result = await cache_aware_llm._acall(messages)

    # Should call underlying LLM
    assert fake_llm.call_count == 1
    assert result.generations[0].message.content == "Python is a high-level programming language."

    # Cache should not be populated (no put call)
    cached_result = await semantic_cache.get(query)
    assert cached_result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_disabled_passes_through_integration(cache_aware_llm, fake_llm):
    """Test that cache disabled passes through to underlying."""
    with patch("llm_client.rag.cache_aware_llm.get_semantic_cache", return_value=None):
        cache_disabled = CacheAwareLLMClient(underlying=fake_llm)

        messages = [HumanMessage(content="test query")]
        result = await cache_disabled._acall(messages)

        assert fake_llm.call_count == 1
        assert (
            result.generations[0].message.content == "Python is a high-level programming language."
        )
