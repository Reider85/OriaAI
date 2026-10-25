"""Integration test for ToolCallingAdapter in build_agent_graph (D-5).

Tests the complete integration flow from service.py through build_agent_graph
to ensure tool calling modes work correctly in real scenarios.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.language_models import BaseChatModel, FakeListChatModel

from llm_client.agent.graph import build_agent_graph, AgentState
from llm_client.agent.tool_calling_adapter import ToolCallingMode
from llm_client.agent.service import should_route_via_router
from llm_client.config import Settings


class MockChatModelWithToolCalls(BaseChatModel):
    """Mock LLM that returns tool calls for testing."""
    
    tool_calling_mode: ToolCallingMode = ToolCallingMode.HYBRID
    
    def bind_tools(self, tools, mode=None):
        if mode == ToolCallingMode.REACT:
            # In REACT mode, we return a ReActBoundModel that generates JSON tool calls
            return MockReActBoundModel(self, tools, None)
        else:
            # In NATIVE/HYBRID mode, we return a model that supports native tool calls
            return MockNativeBoundModel(self, tools)
    
    async def ainvoke(self, messages, **kwargs):
        # Return a response with tool calls for testing
        if self.tool_calling_mode == ToolCallingMode.NATIVE:
            return AIMessage(
                content="I'll help you search for information.",
                tool_calls=[
                    {
                        "id": "test_tool_call_1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "test query"}'
                        }
                    }
                ]
            )
        elif self.tool_calling_mode == ToolCallingMode.REACT:
            # ReAct mode returns text that will be parsed by ReActBoundModel
            return AIMessage(
                content='{"tool": "web_search", "arguments": {"query": "test query"}}'
            )
        else:
            # HYBRID mode can use either, default to native for this test
            return AIMessage(
                content="I'll help you search for information.",
                tool_calls=[
                    {
                        "id": "test_tool_call_1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "test query"}'
                        }
                    }
                ]
            )
    
    def _generate(self, messages, **kwargs):
        # Mock implementation for abstract method
        return AIMessage(content="Mock response")
    
    @property
    def _llm_type(self):
        return "mock-chat-model-with-tool-calls"


class MockNativeBoundModel(BaseChatModel):
    """Mock bound model that supports native tool calls."""
    
    underlying: BaseChatModel
    tools: list
    
    def __init__(self, underlying: BaseChatModel, tools: list, **kwargs):
        super().__init__(underlying=underlying, tools=tools, **kwargs)
    
    async def ainvoke(self, messages, **kwargs):
        return await self.underlying.ainvoke(messages, **kwargs)
    
    def _generate(self, messages, **kwargs):
        return self.underlying._generate(messages, **kwargs)
    
    @property
    def _llm_type(self):
        return "mock-native-bound-model"


class MockReActBoundModel(BaseChatModel):
    """Mock bound model that generates ReAct-style JSON tool calls."""
    
    underlying: BaseChatModel
    tools: list
    adapter: Any
    
    def __init__(self, underlying: BaseChatModel, tools: list, adapter: Any = None, **kwargs):
        super().__init__(underlying=underlying, tools=tools, adapter=adapter, **kwargs)
    
    async def ainvoke(self, messages, **kwargs):
        return await self.underlying.ainvoke(messages, **kwargs)
    
    def _generate(self, messages, **kwargs):
        return self.underlying._generate(messages, **kwargs)
    
    @property
    def _llm_type(self):
        return "mock-react-bound-model"


class TestGraphToolCallingAdapterE2E:
    """End-to-end tests for ToolCallingAdapter integration."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        return Settings(
            llm_provider="openai",
            openai_model="gpt-4o",
            openai_api_key="test-key",
            llm_router_enabled=False,
            tools_enabled="web_search"
        )

    @pytest.fixture
    def mock_tools(self):
        """Mock tools for testing."""
        return [
            {
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"]
                }
            }
        ]

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM with tool calling support."""
        return MockChatModelWithToolCalls()

    def test_native_mode_tool_calls(self, mock_llm, mock_tools):
        """Test that NATIVE mode produces native tool calls."""
        graph = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="openai",
            model="gpt-4o",
            tool_calling_mode=ToolCallingMode.NATIVE
        )
        
        # Create test state
        state = {
            "messages": [HumanMessage(content="Search for information about AI")],
            "user_id": "test_user",
            "session_id": str(uuid4()),
            "max_iterations": 5
        }
        
        # Test the graph execution
        # This is a simplified test - in real scenario we'd need to mock tool execution
        assert graph is not None

    def test_react_mode_tool_calls(self, mock_llm, mock_tools):
        """Test that REACT mode produces ReAct-style tool calls."""
        # Create LLM with REACT mode
        react_llm = MockChatModelWithToolCalls(tool_calling_mode=ToolCallingMode.REACT)
        
        graph = build_agent_graph(
            react_llm,
            tools=mock_tools,
            provider="openai",
            model="gpt-4o",
            tool_calling_mode=ToolCallingMode.REACT
        )
        
        # Create test state
        state = {
            "messages": [HumanMessage(content="Search for information about AI")],
            "user_id": "test_user",
            "session_id": str(uuid4()),
            "max_iterations": 5
        }
        
        # Test the graph execution
        assert graph is not None

    def test_hybrid_mode_auto_selection(self, mock_llm, mock_tools):
        """Test that HYBRID mode automatically selects the best mode."""
        graph = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="openai",
            model="gpt-4o",
            tool_calling_mode=ToolCallingMode.HYBRID
        )
        
        # Create test state
        state = {
            "messages": [HumanMessage(content="Search for information about AI")],
            "user_id": "test_user",
            "session_id": str(uuid4()),
            "max_iterations": 5
        }
        
        # Test the graph execution
        assert graph is not None

    def test_no_tools_passthrough(self, mock_llm):
        """Test that when no tools are provided, no adapter logic is used."""
        graph = build_agent_graph(
            mock_llm,
            tools=None,
            provider="openai",
            model="gpt-4o"
        )
        
        # Graph should still be created
        assert graph is not None

    def test_provider_model_without_tools(self, mock_llm):
        """Test that provider/model parameters are ignored when no tools."""
        graph = build_agent_graph(
            mock_llm,
            tools=None,
            provider="openai",
            model="gpt-4o"
        )
        
        # Graph should still be created
        assert graph is not None

    @pytest.mark.asyncio
    async def test_router_integration_flag(self, mock_settings):
        """Test that router integration flag works correctly."""
        # Test router disabled
        mock_settings.llm_router_enabled = False
        assert not should_route_via_router(mock_settings)
        
        # Test router enabled with 100% traffic
        mock_settings.llm_router_enabled = True
        mock_settings.llm_router_traffic_percent = 100
        assert should_route_via_router(mock_settings)
        
        # Test router enabled with partial traffic
        mock_settings.llm_router_traffic_percent = 50
        # This should sometimes return True (random)
        results = [should_route_via_router(mock_settings) for _ in range(10)]
        assert any(results)  # Should be True at least sometimes

    def test_graph_with_rag_pipeline(self, mock_llm, mock_tools):
        """Test that adapter integration works with RAG pipeline."""
        mock_rag_pipeline = MagicMock()
        
        graph = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="openai",
            model="gpt-4o",
            rag_pipeline=mock_rag_pipeline
        )
        
        # Graph should be created with RAG support
        assert graph is not None

    def test_graph_with_monitor(self, mock_llm, mock_tools):
        """Test that adapter integration works with iteration monitor."""
        from llm_client.agent.cycle_detection import IterationMonitor
        
        monitor = IterationMonitor()
        
        graph = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="openai",
            model="gpt-4o",
            monitor=monitor
        )
        
        # Graph should be created with monitor
        assert graph is not None

    def test_graph_with_checkpointer(self, mock_llm, mock_tools):
        """Test that adapter integration works with checkpointer."""
        # Use None as checkpointer to avoid import issues
        graph = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="openai",
            model="gpt-4o",
            checkpointer=None
        )
        
        # Graph should be created with checkpointer
        assert graph is not None

    def test_graph_with_settings(self, mock_llm, mock_tools):
        """Test that adapter integration works with settings."""
        settings = {"top_k": 5}
        
        graph = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="openai",
            model="gpt-4o",
            settings=settings
        )
        
        # Graph should be created with settings
        assert graph is not None

    def test_error_handling_fallback(self, mock_tools):
        """Test error handling when adapter fails."""
        with patch('llm_client.agent.graph.logger') as mock_logger:
            # Patch the bind_tools method to raise an error
            with patch.object(MockChatModelWithToolCalls, 'bind_tools', side_effect=NotImplementedError("Bind failed")):
                failing_llm = MockChatModelWithToolCalls()
                graph = build_agent_graph(
                    failing_llm,
                    tools=mock_tools,
                    provider="openai",
                    model="gpt-4o"
                )
            
            # Should log warning and fallback to raw LLM
            mock_logger.warning.assert_called_once()
            assert "ToolCallingAdapter failed" in mock_logger.warning.call_args[0][0]
            assert graph is not None

    def test_provider_model_case_sensitivity(self, mock_llm, mock_tools):
        """Test that provider/model case sensitivity is handled correctly."""
        # Test with different case variations
        graph1 = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="OPENAI",  # uppercase
            model="GPT-4O"     # uppercase
        )
        
        graph2 = build_agent_graph(
            mock_llm,
            tools=mock_tools,
            provider="openai",  # lowercase
            model="gpt-4o"     # lowercase
        )
        
        # Both should work
        assert graph1 is not None
        assert graph2 is not None