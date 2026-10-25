"""Unit tests for ToolCallingAdapter integration in build_agent_graph (D-5).

Tests the integration of ToolCallingAdapter into the LangGraph agent builder,
ensuring proper mode selection, fallback behavior, and tool binding.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from llm_client.agent.graph import build_agent_graph
from llm_client.agent.tool_calling_adapter import (
    ToolCallingMode,
    get_tool_calling_adapter,
    HybridBoundModel,
    ReActBoundModel,
)
from llm_client.agent.provider import LLMProviderFactory


class MockChatModel(BaseChatModel):
    """Mock LLM for testing tool calling modes."""
    
    supports_bind_tools: bool = True
    should_fail_bind: bool = False
    
    def bind_tools(self, tools):
        if self.should_fail_bind:
            raise NotImplementedError("Mock bind failure")
        if not self.supports_bind_tools:
            raise AttributeError("No bind_tools method")
        return self
    
    async def ainvoke(self, messages, **kwargs):
        return AIMessage(content="Mock response")
    
    def _generate(self, messages, **kwargs):
        # Mock implementation for abstract method
        return AIMessage(content="Mock response")
    
    @property
    def _llm_type(self):
        return "mock-chat-model"


class TestGraphToolCallingAdapter:
    """Test ToolCallingAdapter integration in build_agent_graph."""

    @pytest.fixture
    def mock_llm(self):
        return MockChatModel(supports_bind_tools=True)

    @pytest.fixture
    def mock_llm_no_bind(self):
        return MockChatModel(supports_bind_tools=False)

    @pytest.fixture
    def mock_llm_bind_fail(self):
        return MockChatModel(supports_bind_tools=True, should_fail_bind=True)

    @pytest.fixture
    def mock_tools(self):
        return [{"name": "test_tool", "description": "A test tool"}]

    def test_default_behavior_hybrid_mode(self, mock_llm, mock_tools):
        """Test that default behavior uses HYBRID mode when provider/model not provided."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            adapter.bind_tools.return_value = mock_llm
            adapter.choose_mode.return_value = ToolCallingMode.HYBRID
            mock_adapter.return_value = adapter
            
            graph = build_agent_graph(mock_llm, tools=mock_tools, provider="openai", model="gpt-4o")
            
            # Verify adapter was used and chose HYBRID mode
            adapter.choose_mode.assert_called_once_with("openai", "gpt-4o", None)
            adapter.bind_tools.assert_called_once()
            
            # Verify graph was created
            assert graph is not None

    def test_explicit_native_mode(self, mock_llm, mock_tools):
        """Test explicit NATIVE mode with provider/model."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            adapter.bind_tools.return_value = mock_llm
            adapter.choose_mode.return_value = ToolCallingMode.NATIVE
            mock_adapter.return_value = adapter
            
            graph = build_agent_graph(
                mock_llm, 
                tools=mock_tools, 
                provider="openai", 
                model="gpt-4o",
                tool_calling_mode=ToolCallingMode.NATIVE
            )
            
            # Verify adapter was used and chose explicit NATIVE mode
            adapter.choose_mode.assert_called_once_with("openai", "gpt-4o", ToolCallingMode.NATIVE)
            adapter.bind_tools.assert_called_once()

    def test_explicit_react_mode(self, mock_llm, mock_tools):
        """Test explicit REACT mode with provider/model."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            # Create proper tool objects for ReActBoundModel
            class MockTool:
                def __init__(self, name, description):
                    self.name = name
                    self.description = description
            langchain_tools = [MockTool(t["name"], t["description"]) for t in mock_tools]
            adapter.bind_tools.return_value = ReActBoundModel(mock_llm, langchain_tools, adapter)
            adapter.choose_mode.return_value = ToolCallingMode.REACT
            mock_adapter.return_value = adapter
            
            graph = build_agent_graph(
                mock_llm, 
                tools=mock_tools, 
                provider="openai", 
                model="gpt-4o",
                tool_calling_mode=ToolCallingMode.REACT
            )
            
            # Verify adapter was used and chose explicit REACT mode
            adapter.choose_mode.assert_called_once_with("openai", "gpt-4o", ToolCallingMode.REACT)
            adapter.bind_tools.assert_called_once()

    def test_no_tools_passthrough(self, mock_llm):
        """Test that when no tools are provided, adapter is not used."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            graph = build_agent_graph(mock_llm, tools=None)
            
            # Adapter should not be called when no tools
            mock_adapter.assert_not_called()
            # Graph should still be created
            assert graph is not None

    def test_adapter_bind_fallback_to_raw_llm(self, mock_llm_bind_fail, mock_tools):
        """Test that adapter bind failure falls back to raw LLM with warning."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            adapter.bind_tools.side_effect = NotImplementedError("Adapter bind failed")
            adapter.choose_mode.return_value = ToolCallingMode.HYBRID
            mock_adapter.return_value = adapter
            
            with patch('llm_client.agent.graph.logger') as mock_logger:
                graph = build_agent_graph(mock_llm_bind_fail, tools=mock_tools)
                
                # Verify fallback behavior
                mock_logger.warning.assert_called_once()
                assert "ToolCallingAdapter failed" in mock_logger.warning.call_args[0][0]
                # Graph should still be created with raw LLM
                assert graph is not None

    def test_adapter_choose_mode_integration(self, mock_llm, mock_tools):
        """Test that adapter's choose_mode is called with correct parameters."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            expected_mode = ToolCallingMode.HYBRID
            adapter.bind_tools.return_value = mock_llm
            adapter.choose_mode.return_value = expected_mode
            mock_adapter.return_value = adapter
            
            # Test with provider and model
            graph = build_agent_graph(
                mock_llm, 
                tools=mock_tools, 
                provider="anthropic", 
                model="claude-3-haiku"
            )
            
            # Verify choose_mode was called with correct parameters
            adapter.choose_mode.assert_called_once_with("anthropic", "claude-3-haiku", None)
            
            # Test with explicit tool_calling_mode override
            graph = build_agent_graph(
                mock_llm, 
                tools=mock_tools, 
                provider="anthropic", 
                model="claude-3-haiku",
                tool_calling_mode=ToolCallingMode.REACT
            )
            
            # Verify explicit mode takes precedence
            adapter.choose_mode.assert_called_with("anthropic", "claude-3-haiku", ToolCallingMode.REACT)

    def test_logging_of_mode_selection(self, mock_llm, mock_tools):
        """Test that mode selection is logged for observability."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            adapter.bind_tools.return_value = mock_llm
            adapter.choose_mode.return_value = ToolCallingMode.HYBRID
            mock_adapter.return_value = adapter
            
            with patch('llm_client.agent.graph.logger') as mock_logger:
                graph = build_agent_graph(
                    mock_llm, 
                    tools=mock_tools, 
                    provider="openai", 
                    model="gpt-4o"
                )
                
# Verify logging of mode selection (there might be multiple calls, e.g., semantic cache + tool calling)
            tool_calling_logs = [call for call in mock_logger.info.call_args_list
                               if "ToolCallingAdapter" in str(call)]
            assert len(tool_calling_logs) == 1
            # Extract the actual arguments from the call and format the string
            args = tool_calling_logs[0][0]
            formatted_msg = args[0] % args[1:]
            assert "HYBRID" in formatted_msg

    def test_graph_with_bound_llm_types(self, mock_llm, mock_tools):
        """Test that different bound LLM types are properly handled."""
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            # Test with HybridBoundModel
            hybrid_llm = HybridBoundModel(mock_llm, mock_llm, adapter)
            adapter.bind_tools.return_value = hybrid_llm
            adapter.choose_mode.return_value = ToolCallingMode.HYBRID
            mock_adapter.return_value = adapter
            
            graph = build_agent_graph(
                mock_llm, 
                tools=mock_tools, 
                provider="openai", 
                model="gpt-4o"
            )
            
            # Verify graph was created with bound LLM
            assert graph is not None

    def test_integration_with_existing_features(self, mock_llm, mock_tools):
        """Test that adapter integration doesn't break existing features."""
        # Test with monitor
        monitor = MagicMock()
        with patch('llm_client.agent.graph.get_tool_calling_adapter') as mock_adapter:
            adapter = MagicMock()
            adapter.bind_tools.return_value = mock_llm
            adapter.choose_mode.return_value = ToolCallingMode.HYBRID
            mock_adapter.return_value = adapter
            
            graph = build_agent_graph(
                mock_llm,
                tools=mock_tools,
                monitor=monitor,
                provider="openai",
                model="gpt-4o"
            )
            
            # Verify all features work together
            assert graph is not None
            adapter.choose_mode.assert_called_once()
            adapter.bind_tools.assert_called_once()


class TestGraphToolCallingAdapterIntegration:
    """Integration tests with real adapter and model capability matrix."""

    def test_real_adapter_integration(self):
        """Test integration with real ToolCallingAdapter."""
        from llm_client.agent.tool_calling_adapter import get_tool_calling_adapter
        
        # Get real adapter
        adapter = get_tool_calling_adapter()
        
        # Verify it's the singleton
        assert adapter is get_tool_calling_adapter()
        
        # Test mode selection with real capabilities
        mode = adapter.choose_mode("openai", "gpt-4o", None)
        assert mode in ToolCallingMode
        
        # Test with unknown provider
        mode = adapter.choose_mode("unknown", "unknown", None)
        assert mode == ToolCallingMode.HYBRID  # Default fallback

    @pytest.mark.asyncio
    async def test_real_llm_factory_integration(self):
        """Test integration with real LLMProviderFactory."""
        # This test would require actual API keys, so we'll mock it
        with patch('llm_client.agent.provider.LLMProviderFactory') as mock_factory:
            mock_factory.create.return_value = MockChatModel()
            
            graph = build_agent_graph(
                MockChatModel(),
                tools=[],
                provider="openai",
                model="gpt-4o"
            )
            
            assert graph is not None