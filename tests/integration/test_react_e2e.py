"""Integration tests for ReAct tool calling (D-3)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool, tool

from llm_client.agent.tool_calling_adapter import ToolCallingAdapter, get_tool_calling_adapter
from llm_client.agent.tool_calling_mode import ToolCallingMode


@tool
def web_search(query: str) -> str:
    """Search the web for information.
    
    Args:
        query: Search query
        
    Returns:
        Search results
    """
    return f"Search results for: {query}"


@tool
def rag_query(query: str) -> str:
    """Query the RAG system for information.
    
    Args:
        query: Query string
        
    Returns:
        RAG results
    """
    return f"RAG results for: {query}"


class TestReactE2E:
    """End-to-end tests for ReAct tool calling."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_react_e2e_extracts_tool_call_from_text_with_fences(self):
        """Test that ReActBoundModel extracts tool call from text with fences."""
        adapter = get_tool_calling_adapter()
        
# Create fake LLM that returns text with JSON tool call
        fake_llm = FakeListChatModel(responses=[
            """
            I need to search for current information.
    
            ```json
            {
              "tool": "web_search",
              "arguments": {
                "query": "current weather in London"
              }
            }
            ```
            """
        ])
        
        # Bind tools with REACT mode
        react_model = adapter.bind_tools(fake_llm, [web_search, rag_query], ToolCallingMode.REACT)
        
        # Invoke the model
        result = await react_model.ainvoke([HumanMessage("What's the weather in London?")])
        
        # Verify tool calls are extracted
        assert hasattr(result, "tool_calls") and result.tool_calls
        assert len(result.tool_calls) == 1
        
        tool_call = result.tool_calls[0]
        assert tool_call["name"] == "web_search"
        assert tool_call["args"] == {"query": "current weather in London"}
        assert tool_call["id"].startswith("react_")
        
        # Verify additional_kwargs contains raw tool calls
        assert "tool_calls" in result.additional_kwargs
        assert len(result.additional_kwargs["tool_calls"]) == 1
        
        raw_tool_call = result.additional_kwargs["tool_calls"][0]
        assert raw_tool_call["function"]["name"] == "web_search"
        assert json.loads(raw_tool_call["function"]["arguments"]) == {"query": "current weather in London"}
        
        # Test tool execution
        tool_result = await web_search.ainvoke(tool_call["args"])
        assert "Search results for: current weather in London" in tool_result

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_react_e2e_extracts_tool_call_from_text_without_fences(self):
        """Test that ReActBoundModel extracts tool call from text without fences."""
        adapter = get_tool_calling_adapter()
        
# Create fake LLM that returns text with JSON tool call without fences
        fake_llm = FakeListChatModel(responses=[
            """
            I need to query the RAG system for information.
    
            {
              "tool": "rag_query",
              "arguments": {
                "query": "latest AI research papers"
              }
            }
            """
        ])
        
        # Bind tools with REACT mode
        react_model = adapter.bind_tools(fake_llm, [web_search, rag_query], ToolCallingMode.REACT)
        
        # Invoke the model
        result = await react_model.ainvoke([HumanMessage("Find latest AI research papers")])
        
        # Verify tool calls are extracted
        assert hasattr(result, "tool_calls") and result.tool_calls
        assert len(result.tool_calls) == 1
        
        tool_call = result.tool_calls[0]
        assert tool_call["name"] == "rag_query"
        assert tool_call["args"] == {"query": "latest AI research papers"}
        assert tool_call["id"].startswith("react_")
        
        # Verify additional_kwargs contains raw tool calls
        assert "tool_calls" in result.additional_kwargs
        assert len(result.additional_kwargs["tool_calls"]) == 1
        
        raw_tool_call = result.additional_kwargs["tool_calls"][0]
        assert raw_tool_call["function"]["name"] == "rag_query"
        assert json.loads(raw_tool_call["function"]["arguments"]) == {"query": "latest AI research papers"}
        
        # Test tool execution
        tool_result = await rag_query.ainvoke(tool_call["args"])
        assert "RAG results for: latest AI research papers" in tool_result

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_react_e2e_no_tool_call(self):
        """Test that ReActBoundModel returns normal response when no tool call."""
        adapter = get_tool_calling_adapter()
        
        # Create fake LLM that returns normal text
        fake_llm = FakeListChatModel(responses=[
            "Hello! I'm here to help you with your questions. What would you like to know?"
        ])
        
        # Bind tools with REACT mode
        react_model = adapter.bind_tools(fake_llm, [web_search, rag_query], ToolCallingMode.REACT)
        
        # Invoke the model
        result = await react_model.ainvoke([HumanMessage("Hello, how are you?")])
        
        # Verify no tool calls are extracted
        assert result.content == "Hello! I'm here to help you with your questions. What would you like to know?"
        assert not hasattr(result, "tool_calls") or not result.tool_calls
        assert "tool_calls" not in result.additional_kwargs or not result.additional_kwargs["tool_calls"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_react_e2e_system_prompt_injection(self):
        """Test that ReAct system prompt is properly injected."""
        adapter = get_tool_calling_adapter()
        
        # Create fake LLM that captures messages
        captured_messages = []
        
        class CapturingChatModel(FakeListChatModel):
            def _generate(self, messages, **kwargs):
                captured_messages.extend(messages)
                return super()._generate(messages, **kwargs)
        
        fake_llm = CapturingChatModel(responses=["Hello world"])
        
        # Bind tools with REACT mode
        react_model = adapter.bind_tools(fake_llm, [web_search, rag_query], ToolCallingMode.REACT)
        
        # Invoke the model
        await react_model.ainvoke([HumanMessage("Hello")])
        
        # Verify system prompt was injected
        assert len(captured_messages) == 2
        assert isinstance(captured_messages[0], HumanMessage) is False  # It should be SystemMessage
        assert "web_search" in captured_messages[0].content
        assert "rag_query" in captured_messages[0].content
        assert "Search the web for information" in captured_messages[0].content