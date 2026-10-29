"""Integration tests for LLMRouter (C-2 ADR-015)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llm_client.agent.router import LLMRouter, RoutingPolicy, get_llm_router
from llm_client.agent.model_cost_table import ModelCostTable, ModelCost
from llm_client.observability.llm_metrics import update_error_rate, update_budget_usage


class TestLLMRouterIntegration:
    """Integration tests with real Prometheus metrics and mocked factory."""

    def setup_method(self):
        """Reset singleton and clear metrics for each test."""
        import llm_client.agent.router as router_module

        router_module._router = None

        # Reset circuit breaker singleton
        import llm_client.agent.circuit_breaker as cb_module

        cb_module._breaker = None

        # Clear Prometheus metrics
        from llm_client.observability.llm_metrics import LLM_ERROR_RATE, LLM_MONTHLY_BUDGET_USAGE

        LLM_ERROR_RATE.clear()
        LLM_MONTHLY_BUDGET_USAGE.clear()

    def test_integration_route_with_real_metrics_and_mock_factory(self):
        """Test routing with real Prometheus metrics and mocked factory."""
        # Create cost table
        cost_table = ModelCostTable()
        cost_table.costs = {
            "openai": {
                "gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60),
                "gpt-4o": ModelCost(prompt=2.50, completion=10.00),
            }
        }

        # Create router with mock factory
        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Test routing
            decision = asyncio.run(router.route(policy=RoutingPolicy.COST))

            # Verify decision
            assert decision.provider == "openai"
            assert decision.model == "gpt-4o-mini"
            assert decision.policy == RoutingPolicy.COST
            assert "cheapest" in decision.reason.lower()

            # Test creating LLM (this is where factory gets called)
            llm = asyncio.run(router.create_llm(decision))
            mock_factory.create.assert_called_once_with(
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-test-placeholder",  # Test API key from settings
            )

    def test_integration_circuit_breaker_with_real_gauge(self):
        """Test circuit breaker with real Prometheus gauge."""
        # Create cost table
        cost_table = ModelCostTable()
        cost_table.costs = {"openai": {"gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60)}}

        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Set error rate to 60% (should trigger circuit breaker)
            update_error_rate("openai", 60, 100)  # 60% error rate

            # Test routing
            decision = asyncio.run(router.route())

            # Should have fallen back to anthropic
            assert decision.provider == "anthropic"
            assert decision.model == "claude-3-haiku"
            assert "circuit breaker" in decision.reason.lower()

    def test_integration_budget_usage_with_real_gauge(self):
        """Test budget usage updates real Prometheus gauge."""
        cost_table = ModelCostTable()
        cost_table.costs = {"openai": {"gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60)}}

        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Record some costs
            asyncio.run(router.record_cost(25.0))
            asyncio.run(router.record_cost(10.0))

            # Budget gauge should show 35% usage (35/100)
            from llm_client.observability.llm_metrics import LLM_MONTHLY_BUDGET_USAGE

            gauge_value = LLM_MONTHLY_BUDGET_USAGE._value.get()
            assert gauge_value == 0.35  # 35% usage

    def test_integration_cost_guard_at_80_percent(self):
        """Test cost guard triggers at 80% budget."""
        cost_table = ModelCostTable()
        cost_table.costs = {
            "openai": {
                "gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60),
                "gpt-4o": ModelCost(prompt=2.50, completion=10.00),
            }
        }

        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Set spent to 80% of budget (should trigger cost guard)
            router._spent_usd = 80.0

            # Test with quality policy (should still return cheapest due to cost guard)
            decision = asyncio.run(router.route(policy=RoutingPolicy.QUALITY))

            # Should have switched to cheapest regardless of policy
            assert decision.provider == "openai"
            assert decision.model == "gpt-4o-mini"
            assert decision.policy == RoutingPolicy.COST  # Policy forced to COST
            assert "budget" in decision.reason.lower()
            assert "switched" in decision.reason.lower()

    def test_integration_singleton_behavior(self):
        """Test that get_llm_router returns the same instance."""
        # Get first instance
        router1 = get_llm_router()

        # Get second instance
        router2 = get_llm_router()

        # Should be the same instance
        assert router1 is router2

    def test_integration_budget_record_and_update(self):
        """Test budget recording and Prometheus gauge updates."""
        cost_table = ModelCostTable()
        cost_table.costs = {"openai": {"gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60)}}

        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=200.0,
            )

            # Record costs
            asyncio.run(router.record_cost(50.0))
            asyncio.run(router.record_cost(30.0))

            # Check internal state
            assert router._spent_usd == 80.0

            # Check Prometheus gauge
            from llm_client.observability.llm_metrics import LLM_MONTHLY_BUDGET_USAGE

            gauge_value = LLM_MONTHLY_BUDGET_USAGE._value.get()
            assert gauge_value == 0.4  # 80/200 = 40%

    def test_integration_fallback_provider_chain(self):
        """Test fallback provider chain works correctly."""
        cost_table = ModelCostTable()
        cost_table.costs = {
            "openai": {"gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60)},
            "anthropic": {"claude-3-haiku": ModelCost(prompt=0.25, completion=1.25)},
        }

        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Test fallback mapping
            assert router._fallback_provider("openai") == ("anthropic", "claude-3-haiku")
            assert router._fallback_provider("anthropic") == ("openai", "gpt-4o-mini")
            assert router._fallback_provider("unknown") is None

    def test_integration_privacy_routing(self):
        """Test privacy routing returns correct provider."""
        cost_table = ModelCostTable()
        cost_table.costs = {"openai": {"gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60)}}

        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Test privacy routing
            decision = asyncio.run(router.route(privacy_required=True))

            assert decision.provider == "custom-openai"
            assert decision.model == "default"
            assert decision.policy == RoutingPolicy.PRIVACY
            assert "privacy" in decision.reason.lower()

    def test_integration_error_handling_circuit_breaker(self):
        """Test error handling in circuit breaker check."""
        cost_table = ModelCostTable()
        cost_table.costs = {"openai": {"gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60)}}

        with patch("llm_client.agent.router.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()

            router = LLMRouter(
                provider_factory=mock_factory,
                cost_table=cost_table,
                budget_usd=100.0,
            )

            # Mock gauge to raise an exception
            # Test error handling in circuit breaker check (simulates gauge read failure)
            with patch("llm_client.observability.llm_metrics.LLM_ERROR_RATE") as mock_error_rate:
                mock_error_rate.labels.side_effect = AttributeError("Gauge read failed")

                # Should not raise exception, should return False (graceful fallback)
                result = asyncio.run(router._check_circuit_breaker("openai"))
                assert result is False
