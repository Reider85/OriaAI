"""Integration tests for ADR-015 Anthropic provider (mocked, no docker services)."""

# NOTE: These tests require real Anthropic API access and are disabled in CI.
# They are kept as documentation for future manual verification.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_anthropic import ChatAnthropic

from llm_client.agent.router import LLMRouter, RoutingPolicy, get_llm_router
from llm_client.agent.model_cost_table import ModelCostTable, ModelCost


class TestAnthropicProviderIntegration:
    '''Integration tests with mocked ChatAnthropic.'''

    def setup_method(self):
        '''Reset singleton for each test.'''
        import llm_client.agent.router as router_module
        router_module._router = None

    @pytest.mark.integration
    def test_integration_factory_returns_mock_anthropic(self):
        '''Test factory returns mocked ChatAnthropic for anthropic provider.'''
        mock_anthropic = MagicMock(spec=ChatAnthropic)
        mock_anthropic.model = "claude-3-haiku"
        mock_anthropic.streaming = True

        with patch("llm_client.agent.provider.ChatAnthropic", return_value=mock_anthropic):
            llm = LLMProviderFactory.create("anthropic", "claude-3-haiku", api_key="sk-ant-test")
            assert llm is mock_anthropic
            assert llm.model == "claude-3-haiku"
            assert llm.streaming is True
            # Verify ChatAnthropic was called with correct args
            mock_anthropic.assert_called_once()
            call_args = mock_anthropic.call_args
            assert call_args[1]["model"] == "claude-3-haiku"
            assert call_args[1]["api_key"].get_secret_value() == "sk-ant-test"

    @pytest.mark.integration
    def test_integration_circuit_breaker_fallback_to_anthropic(self):
        '''Test circuit breaker fallback route to anthropic, factory returns mock.'''
        mock_anthropic = MagicMock(spec=ChatAnthropic)
        mock_anthropic.model = "claude-3-haiku"

        with patch("llm_client.agent.provider.ChatAnthropic", return_value=mock_anthropic):
            # Create cost table
            cost_table = ModelCostTable()
            cost_table.costs = {
                "openai": {
                    "gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60),
                    "gpt-4o": ModelCost(prompt=2.50, completion=10.00),
                },
                "anthropic": {
                    "claude-3-haiku": ModelCost(prompt=0.25, completion=1.25),
                }
            }

            router = LLMRouter(
                provider_factory=LLMProviderFactory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Set error rate to 60% (should trigger circuit breaker)
            from llm_client.observability.llm_metrics import update_error_rate
            update_error_rate("openai", 60, 100)  # 60% error rate

            # Test routing
            decision = router.route()

            # Should have fallen back to anthropic
            assert decision.provider == "anthropic"
            assert decision.model == "claude-3-haiku"
            assert "circuit breaker" in decision.reason.lower()

            # Test creating LLM via factory (should return mock)
            llm = router.create_llm(decision)
            assert llm is mock_anthropic
            assert llm.model == "claude-3-haiku"
"""
