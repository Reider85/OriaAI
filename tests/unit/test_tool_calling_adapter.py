"""Unit tests for ToolCallingAdapter."""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, Mock, sentinel

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, tool

from llm_client.agent.capability_matrix import ModelCapabilities, ModelCapabilityMatrix
from llm_client.agent.tool_calling_adapter import (
    HybridBoundModel,
    ReActBoundModel,
    ToolCallingAdapter,
    get_tool_calling_adapter,
    _to_openai_tool_call,
)
from llm_client.agent.tool_calling_mode import ToolCallingMode


class FakeCapabilityMatrix(ModelCapabilityMatrix):
    """Test capability matrix with controlled entries."""

    def __init__(self):
        # Create a minimal matrix for testing
        super().__init__()

    def get_capabilities(self, provider: str, model: str) -> ModelCapability | None:
        """Return controlled capabilities for testing."""
        if provider == "openai" and model == "gpt-4o-mini":
            return ModelCapabilities(
                supports_native_tools=True,
                supports_streaming=True,
                cost_per_1m_tokens={"prompt": 0.15, "completion": 0.6},
            )
        elif provider == "ollama" and model == "llama3.1-8b":
            return ModelCapabilities(
                supports_native_tools=False,
                supports_streaming=True,
                cost_per_1m_tokens={"prompt": 0.1, "completion": 0.2},
            )
        elif provider == "unknown" and model == "nope":
            return None
        return None


@tool
def fake_tool(query: str) -> str:
    """Fake tool for testing."""
    return f"Result for {query}"


class MockChatModel:
    """Mock chat model for testing."""

    def __init__(self, responses=None, bind_tools_result=None):
        self.responses = responses or []
        self.bind_tools_result = bind_tools_result or self
        self._bind_tools_called_with = None
        self._generate_calls = []
        self._ainvoke_calls = []

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.outputs import ChatGeneration, ChatResult

        self._generate_calls.append(messages)
        content = self.responses.pop(0) if self.responses else "Hello world"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.outputs import ChatGeneration, ChatResult

        content = self.responses.pop(0) if self.responses else "Hello world"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    def bind_tools(self, tools, **kwargs):
        self._bind_tools_called_with = tools
        return self.bind_tools_result or self

    async def ainvoke(self, messages, **kwargs):
        from langchain_core.outputs import ChatGeneration, ChatResult

        self._ainvoke_calls.append(messages)
        content = self.responses.pop(0) if self.responses else "Hello world"
        return AIMessage(content=content)

    async def astream(self, messages, **kwargs):
        from langchain_core.messages import AIMessage
        
        if self.responses:
            content = self.responses.pop(0)
        else:
            content = "Hello world"
        
        yield AIMessage(content=content)


class TestToolCallingAdapter:
    """Test ToolCallingAdapter functionality."""

    def test_choose_mode_native_support_returns_hybrid(self):
        """Test that gpt-4o-mini defaults to HYBRID mode."""
        adapter = ToolCallingAdapter(FakeCapabilityMatrix())
        mode = adapter.choose_mode("openai", "gpt-4o-mini")
        assert mode == ToolCallingMode.HYBRID

    def test_choose_mode_no_native_returns_react(self):
        """Test that llama3.1-8b defaults to REACT mode."""
        adapter = ToolCallingAdapter(FakeCapabilityMatrix())
        mode = adapter.choose_mode("ollama", "llama3.1-8b")
        assert mode == ToolCallingMode.REACT

    def test_choose_mode_explicit_override(self):
        """Test that explicit mode overrides capability matrix."""
        adapter = ToolCallingAdapter(FakeCapabilityMatrix())
        mode = adapter.choose_mode("openai", "gpt-4o-mini", ToolCallingMode.REACT)
        assert mode == ToolCallingMode.REACT

    def test_choose_mode_unknown_model_defaults_to_hybrid(self):
        """Test that unknown model defaults to HYBRID with warning."""
        adapter = ToolCallingAdapter(FakeCapabilityMatrix())
        mode = adapter.choose_mode("unknown", "nope")
        assert mode == ToolCallingMode.HYBRID

    def test_bind_tools_native_mode_returns_bound_model(self):
        """Test that NATIVE mode returns bound model."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel()
        mock_bound = Mock()
        mock_llm.bind_tools_result = mock_bound
        
        result = adapter.bind_tools(mock_llm, [fake_tool], ToolCallingMode.NATIVE)
        
        assert result == mock_bound
        assert mock_llm._bind_tools_called_with == [fake_tool]

    def test_bind_tools_react_mode_returns_react_bound_model(self):
        """Test that REACT mode returns ReActBoundModel."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel()
        
        result = adapter.bind_tools(mock_llm, [fake_tool], ToolCallingMode.REACT)
        
        assert isinstance(result, ReActBoundModel)
        assert result._underlying == mock_llm
        assert len(result._tools) == 1
        assert result._tools[0] == fake_tool

    def test_bind_tools_hybrid_mode_returns_hybrid_bound_model(self):
        """Test that HYBRID mode returns HybridBoundModel."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel()
        mock_native_bound = Mock()
        mock_llm.bind_tools_result = mock_native_bound
        
        result = adapter.bind_tools(mock_llm, [fake_tool], ToolCallingMode.HYBRID)
        
        assert isinstance(result, HybridBoundModel)
        assert result._native_bound == mock_native_bound
        assert isinstance(result._react_bound, ReActBoundModel)

    def test_bind_tools_hybrid_falls_back_to_react_on_bind_error(self):
        """Test that HYBRID falls back to ReAct on bind error."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel()
        def bind_tools_failure(*args, **kwargs):
            raise Exception("Bind failed")
        mock_llm.bind_tools = bind_tools_failure
        
        result = adapter.bind_tools(mock_llm, [fake_tool], ToolCallingMode.HYBRID)
        
        assert isinstance(result, ReActBoundModel)
        assert result._underlying == mock_llm

    def test_bind_tools_unknown_mode_raises_value_error(self):
        """Test that unknown mode raises ValueError."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel()
        
        with pytest.raises(ValueError, match="'unknown' is not a valid ToolCallingMode"):
            adapter.bind_tools(mock_llm, [fake_tool], ToolCallingMode("unknown"))

    def test_parse_react_response_extracts_json_with_fences(self):
        """Test that parse_react_response extracts JSON with fences."""
        adapter = ToolCallingAdapter()
        response = """
        I need to search for information.
        
        ```json
        {
          "tool": "web_search",
          "arguments": {
            "query": "current weather in London"
          }
        }
        ```
        """
        
        result = adapter.parse_react_response(response)
        assert result is not None
        assert result["tool"] == "web_search"
        assert result["arguments"]["query"] == "current weather in London"

    def test_parse_react_response_extracts_json_without_fences(self):
        """Test that parse_react_response extracts JSON without fences."""
        adapter = ToolCallingAdapter()
        response = """
        I need to search for information.
        
        {
          "tool": "web_search",
          "arguments": {
            "query": "current weather in London"
          }
        }
        """
        
        result = adapter.parse_react_response(response)
        assert result is not None
        assert result["tool"] == "web_search"
        assert result["arguments"]["query"] == "current weather in London"

    def test_parse_react_response_returns_none_for_no_tool_call(self):
        """Test that parse_react_response returns None for no tool call."""
        adapter = ToolCallingAdapter()
        response = "Hello! How can I help you today?"
        
        result = adapter.parse_react_response(response)
        assert result is None

    def test_build_react_system_prompt_includes_tool_descriptions(self):
        """Test that build_react_system_prompt includes tool descriptions."""
        adapter = ToolCallingAdapter()
        tools = [fake_tool]
        
        prompt = adapter.build_react_system_prompt(tools)
        
        assert "fake_tool" in prompt
        assert "Fake tool for testing" in prompt
        assert "args" in prompt

    def test_get_tool_calling_adapter_is_singleton(self):
        """Test that get_tool_calling_adapter returns the same instance."""
        adapter1 = get_tool_calling_adapter()
        adapter2 = get_tool_calling_adapter()
        
        assert adapter1 is adapter2

    def test_to_openai_tool_call_conversion(self):
        """Test _to_openai_tool_call conversion."""
        tool_call = {
            "tool": "web_search",
            "arguments": {"query": "test"}
        }
        
        result = _to_openai_tool_call(tool_call)
        
        assert "id" in result
        assert result["id"].startswith("react_")
        assert result["function"]["name"] == "web_search"
        assert json.loads(result["function"]["arguments"]) == {"query": "test"}

    async def test_react_bound_model_ainvoke_emits_parsable_tool_call(self):
        """Test that ReActBoundModel.ainvoke emits parsable tool call."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel([
            """
            I need to search for information.
            
            ```json
            {
              "tool": "web_search",
              "arguments": {
                "query": "test query"
              }
            }
            ```
            """
        ])
        
        react_model = adapter.bind_tools(mock_llm, [fake_tool], ToolCallingMode.REACT)
        result = await react_model.ainvoke([HumanMessage("Search for test query")])
        
        # Check that result has tool calls
        assert hasattr(result, "tool_calls") and result.tool_calls
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "web_search"
        assert result.tool_calls[0]["args"] == {"query": "test query"}
        assert result.tool_calls[0]["id"].startswith("react_")
        
        # Check additional_kwargs
        assert "tool_calls" in result.additional_kwargs
        assert len(result.additional_kwargs["tool_calls"]) == 1
        assert result.additional_kwargs["tool_calls"][0]["function"]["name"] == "web_search"
        assert json.loads(result.additional_kwargs["tool_calls"][0]["function"]["arguments"]) == {"query": "test query"}


class TestReActBoundModel:
    """Test ReActBoundModel functionality."""

    async def test_ainvoke_injects_system_prompt(self):
        """Test that ReActBoundModel injects system prompt."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel(["Hello world"])
        react_model = ReActBoundModel(mock_llm, [fake_tool], adapter)
        
        await react_model.ainvoke([HumanMessage("Hello")])
        
        # Check that system prompt was injected
        assert len(mock_llm._ainvoke_calls) == 1
        messages = mock_llm._ainvoke_calls[0]
        assert len(messages) == 2
        assert isinstance(messages[0], SystemMessage)
        assert "fake_tool" in messages[0].content

    async def test_ainvoke_no_tool_call(self):
        """Test that ReActBoundModel returns original response when no tool call."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel(["Hello world"])
        react_model = ReActBoundModel(mock_llm, [fake_tool], adapter)
        
        result = await react_model.ainvoke([HumanMessage("Hello")])
        
        assert result.content == "Hello world"
        assert not hasattr(result, "tool_calls") or not result.tool_calls

    async def test_astream_accumulates_text(self):
        """Test that ReActBoundModel.astream accumulates text correctly."""
        adapter = ToolCallingAdapter()
        mock_llm = MockChatModel(["Hello world"])
        react_model = ReActBoundModel(mock_llm, [fake_tool], adapter)
        
        # Mock the astream method to yield chunks
        chunks = [
            AIMessage(content="Hello"),
            AIMessage(content=" world"),
        ]
        async def async_chunks():
            for chunk in chunks:
                yield chunk
        mock_llm.astream = Mock(return_value=async_chunks())
        
        accumulated = ""
        async for chunk in react_model.astream([HumanMessage("Hello")]):
            if hasattr(chunk, "content"):
                accumulated += chunk.content
        
        assert accumulated == "Hello world"


class TestHybridBoundModel:
    """Test HybridBoundModel functionality."""

    async def test_ainvoke_uses_native_when_available(self):
        """Test that HybridBoundModel uses native when available."""
        adapter = ToolCallingAdapter()
        mock_native = MockChatModel()
        # Create a custom mock that returns a message with tool_calls
        async def mock_ainvoke(messages, **kwargs):
            return AIMessage(
                content="Hello",
                tool_calls=[{"name": "test", "args": {}, "id": "1"}]
            )
        mock_native.ainvoke = mock_ainvoke
        hybrid_model = HybridBoundModel(mock_native, MockChatModel(), adapter)
        
        result = await hybrid_model.ainvoke([HumanMessage("Hello")])
        
        assert result.content == "Hello"
        assert result.tool_calls

    async def test_ainvoke_falls_back_to_react_on_exception(self):
        """Test that HybridBoundModel falls back to ReAct on exception."""
        adapter = ToolCallingAdapter()
        mock_native = MockChatModel()
        def mock_ainvoke_failure(*args, **kwargs):
            raise Exception("Native failed")
        mock_native.ainvoke = mock_ainvoke_failure
        mock_react = MockChatModel()
        mock_react.responses = ["Fallback"]
        hybrid_model = HybridBoundModel(mock_native, mock_react, adapter)
        
        result = await hybrid_model.ainvoke([HumanMessage("Hello")])
        
        assert result.content == "Fallback"