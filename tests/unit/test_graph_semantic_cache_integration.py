"""Unit tests for B-5 semantic cache integration in build_agent_graph."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from llm_client.agent.graph import build_agent_graph
from llm_client.rag.cache_aware_llm import CacheAwareBoundModel, CacheAwareLLMClient


class MockCacheHit:
    """CacheHitResult-compatible object for testing."""

    def __init__(self, answer: str):
        self.answer = answer
        self.referenced_doc_ids = []
        self.created_at = ""
        self.model = "test"
        self.token_count = 0
        self.similarity_score = 1.0


class MockSemanticCache:
    """Mock semantic cache for testing."""

    def __init__(self):
        self.put_called = False
        self.put_kwargs = None
        self._hit_answer: str | None = None

    def set_hit(self, answer: str) -> None:
        self._hit_answer = answer

    async def get(self, query: str) -> MockCacheHit | None:
        if self._hit_answer is not None:
            return MockCacheHit(self._hit_answer)
        return None

    async def put(
        self,
        query: str,
        answer: str,
        referenced_doc_ids=None,
        model: str = "unknown",
        token_count: int = 0,
    ) -> None:
        self.put_called = True
        self.put_kwargs = {
            "query": query,
            "answer": answer,
            "referenced_doc_ids": referenced_doc_ids,
            "model": model,
            "token_count": token_count,
        }


DOC_TOOL_MSG = ToolMessage(
    content=json.dumps(
        {
            "chunks": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "content": "Python is a programming language",
                }
            ]
        }
    ),
    tool_call_id="123",
    name="rag_query",
)


@pytest.fixture
def mock_cache():
    return MockSemanticCache()


@pytest.fixture
def mock_cache_hit():
    c = MockSemanticCache()
    c.set_hit("cached answer")
    return c


@pytest.fixture
def fake_llm():
    return FakeListChatModel(responses=["Hello from LLM"])


# ── build_agent_graph wrapping tests ──────────────────────────────────────────


def test_build_agent_graph_with_cache_wraps_llm():
    with patch(
        "llm_client.rag.cache_aware_llm.CacheAwareLLMClient",
        wraps=CacheAwareLLMClient,
    ) as mock_wrapper:
        llm = FakeListChatModel(responses=["Hello"])
        graph = build_agent_graph(llm, use_semantic_cache=True)
        assert graph is not None
        mock_wrapper.assert_called_once()


def test_build_agent_graph_without_cache_skips_wrapping():
    with patch(
        "llm_client.rag.cache_aware_llm.CacheAwareLLMClient",
        wraps=CacheAwareLLMClient,
    ) as mock_wrapper:
        llm = FakeListChatModel(responses=["Hello"])
        graph = build_agent_graph(llm, use_semantic_cache=False)
        assert graph is not None
        mock_wrapper.assert_not_called()


def test_build_agent_graph_default_uses_settings():
    with (
        patch(
            "llm_client.rag.cache_aware_llm.CacheAwareLLMClient",
            wraps=CacheAwareLLMClient,
        ) as mock_wrapper,
        patch("llm_client.config.settings") as mock_settings,
        patch(
            "llm_client.rag.semantic_cache.get_semantic_cache"
        ) as mock_get_cache,
    ):
        mock_settings.semantic_cache_enabled = True
        mock_get_cache.return_value = MockSemanticCache()
        llm = FakeListChatModel(responses=["Hello"])
        graph = build_agent_graph(llm)
        assert graph is not None
        mock_wrapper.assert_called_once()


def test_build_agent_graph_default_no_cache_skips_wrapping():
    with (
        patch(
            "llm_client.rag.cache_aware_llm.CacheAwareLLMClient",
            wraps=CacheAwareLLMClient,
        ) as mock_wrapper,
        patch("llm_client.config.settings") as mock_settings,
        patch(
            "llm_client.rag.semantic_cache.get_semantic_cache"
        ) as mock_get_cache,
    ):
        mock_settings.semantic_cache_enabled = True
        mock_get_cache.return_value = None
        llm = FakeListChatModel(responses=["Hello"])
        graph = build_agent_graph(llm)
        assert graph is not None
        mock_wrapper.assert_not_called()


# ── CacheAwareLLMClient behaviour tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_aware_llm_cache_hit_returns_cached_answer(fake_llm, mock_cache_hit):
    """CacheAwareLLMClient.ainvoke returns cached answer on hit."""
    with patch(
        "llm_client.rag.cache_aware_llm.get_semantic_cache",
        return_value=mock_cache_hit,
    ):
        client = CacheAwareLLMClient(underlying=fake_llm)
        messages = [
            HumanMessage(content="What is Python?"),
            DOC_TOOL_MSG,
        ]
        result = await client.ainvoke(messages)
        assert result.content == "cached answer"


@pytest.mark.asyncio
async def test_cache_aware_llm_cache_miss_calls_llm_and_caches(fake_llm, mock_cache):
    """CacheAwareLLMClient.ainvoke falls through to LLM on miss, then caches."""
    with (
        patch(
            "llm_client.rag.cache_aware_llm.get_semantic_cache",
            return_value=mock_cache,
        ),
        patch(
            "llm_client.rag.cache_aware_llm._store_in_cache_fire_and_forget"
        ) as mock_store,
    ):
        client = CacheAwareLLMClient(underlying=fake_llm)
        messages = [
            HumanMessage(content="What is Python?"),
            DOC_TOOL_MSG,
        ]
        result = await client.ainvoke(messages)
        assert result.content == "Hello from LLM"
        mock_store.assert_called_once()
        call_kwargs = mock_store.call_args
        assert call_kwargs.kwargs["query"] == "What is Python?"
        assert call_kwargs.kwargs["answer"] == "Hello from LLM"
        assert call_kwargs.kwargs["referenced_doc_ids"]


@pytest.mark.asyncio
async def test_cache_aware_llm_no_doc_ids_bypasses_cache(fake_llm, mock_cache):
    """CacheAwareLLMClient.ainvoke bypasses cache when no referenced_doc_ids."""
    with (
        patch(
            "llm_client.rag.cache_aware_llm.get_semantic_cache",
            return_value=mock_cache,
        ),
        patch(
            "llm_client.rag.cache_aware_llm._store_in_cache_fire_and_forget"
        ) as mock_store,
    ):
        client = CacheAwareLLMClient(underlying=fake_llm)
        messages = [HumanMessage(content="What is the weather?")]
        result = await client.ainvoke(messages)
        assert result.content == "Hello from LLM"
        mock_store.assert_not_called()


@pytest.mark.asyncio
async def test_cache_aware_llm_disabled_passes_through(fake_llm):
    """CacheAwareLLMClient.ainvoke passes through when cache is None."""
    with patch(
        "llm_client.rag.cache_aware_llm.get_semantic_cache",
        return_value=None,
    ):
        client = CacheAwareLLMClient(underlying=fake_llm)
        messages = [HumanMessage(content="Hello")]
        result = await client.ainvoke(messages)
        assert result.content == "Hello from LLM"


# ── CacheAwareBoundModel tests ─────────────────────────────────────────────────


def test_bind_tools_returns_cache_aware_bound_model():
    """bind_tools returns CacheAwareBoundModel wrapping the bound model."""

    class ToolCapableFakeLLM(FakeListChatModel):
        def bind_tools(self, tools, **kwargs):
            return MagicMock()

    underlying = ToolCapableFakeLLM(responses=["test"])
    client = CacheAwareLLMClient(underlying=underlying)
    result = client.bind_tools([MagicMock()])
    assert isinstance(result, CacheAwareBoundModel)


@pytest.mark.asyncio
async def test_bound_model_cache_hit(fake_llm, mock_cache_hit):
    """CacheAwareBoundModel.ainvoke returns cached answer on hit."""
    client = CacheAwareLLMClient(underlying=fake_llm)
    with patch(
        "llm_client.rag.cache_aware_llm.get_semantic_cache",
        return_value=mock_cache_hit,
    ):
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=AIMessage(content="LLM response")
        )
        bound = CacheAwareBoundModel(bound=mock_bound, cache_llm=client)
        messages = [
            HumanMessage(content="What is Python?"),
            DOC_TOOL_MSG,
        ]
        result = await bound.ainvoke(messages)
        assert result.content == "cached answer"
        mock_bound.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_bound_model_cache_miss_calls_bound_and_caches(fake_llm, mock_cache):
    """CacheAwareBoundModel.ainvoke falls through to bound on miss."""
    client = CacheAwareLLMClient(underlying=fake_llm)
    with (
        patch(
            "llm_client.rag.cache_aware_llm.get_semantic_cache",
            return_value=mock_cache,
        ),
        patch(
            "llm_client.rag.cache_aware_llm._store_in_cache_fire_and_forget"
        ) as mock_store,
    ):
        mock_bound = MagicMock()
        mock_bound.ainvoke = AsyncMock(
            return_value=AIMessage(content="LLM response")
        )
        bound = CacheAwareBoundModel(bound=mock_bound, cache_llm=client)
        messages = [
            HumanMessage(content="What is Python?"),
            DOC_TOOL_MSG,
        ]
        result = await bound.ainvoke(messages)
        assert result.content == "LLM response"
        mock_bound.ainvoke.assert_called_once()
        mock_store.assert_called_once()


def test_bound_model_proxy_getattr(fake_llm):
    """CacheAwareBoundModel.__getattr__ proxies to underlying bound model."""
    client = CacheAwareLLMClient(underlying=fake_llm)
    mock_bound = MagicMock()
    mock_bound.some_attr = "proxied"
    bound = CacheAwareBoundModel(bound=mock_bound, cache_llm=client)
    assert bound.some_attr == "proxied"


# ── _extract_referenced_doc_ids tests ─────────────────────────────────────────


def test_extract_doc_ids_from_content_json(fake_llm):
    """_extract_referenced_doc_ids parses ToolMessage.content JSON."""
    client = CacheAwareLLMClient(underlying=fake_llm)
    doc_ids = client._extract_referenced_doc_ids(
        [HumanMessage(content="q"), DOC_TOOL_MSG]
    )
    assert len(doc_ids) == 1
    assert str(doc_ids[0]) == "123e4567-e89b-12d3-a456-426614174000"


def test_extract_doc_ids_no_tool_message(fake_llm):
    """_extract_referenced_doc_ids returns [] without ToolMessages."""
    client = CacheAwareLLMClient(underlying=fake_llm)
    doc_ids = client._extract_referenced_doc_ids([HumanMessage(content="q")])
    assert doc_ids == []


def test_extract_doc_ids_from_metadata(fake_llm):
    """_extract_referenced_doc_ids handles metadata.document_id."""
    client = CacheAwareLLMClient(underlying=fake_llm)
    tool_msg = ToolMessage(
        content=json.dumps(
            {
                "chunks": [
                    {
                        "content": "text",
                        "metadata": {
                            "document_id": "123e4567-e89b-12d3-a456-426614174000"
                        },
                    }
                ]
            }
        ),
        tool_call_id="1",
        name="rag_query",
    )
    doc_ids = client._extract_referenced_doc_ids([tool_msg])
    assert len(doc_ids) == 1
    assert str(doc_ids[0]) == "123e4567-e89b-12d3-a456-426614174000"
