"""Unit tests for LLMRouter migration (C-6 ADR-015)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from llm_client.agent.router import LLMRouter, RoutingDecision, RoutingPolicy, get_llm_router, should_route_via_router
from llm_client.config import Settings


class TestRouterMigration:
    """Test migration feature flags and shadow mode."""

    def setup_method(self):
        """Reset singleton for each test."""
        import llm_client.agent.router as router_module
        router_module._router = None
        # Reset operational writer
        import llm_client.observability.operational_writer as ow
        ow._operational_writer = None

    def test_shadow_mode_logs_decision(self):
        """Test route_shadow writes router_shadow_decision event to operational stream."""
        settings = Settings()
        router = get_llm_router()
        
        # Mock operational writer
        mock_writer = AsyncMock()
        with patch('llm_client.observability.operational_writer.get_operational_writer', return_value=mock_writer):
            decision = asyncio.run(router.route_shadow(policy=RoutingPolicy.COST))
            mock_writer.write.assert_called_once()
            call_args = mock_writer.write.call_args[0][0]
            assert call_args["event_type"] == "router_shadow_decision"
            assert "decision" in call_args
            assert call_args["timestamp"] is not None
            # The actual provider depends on the cost table setup; just verify it's a valid provider
            assert decision.provider in ["openai", "custom-openai", "anthropic"]

    def test_router_disabled_falls_back_to_factory(self):
        """Test llm_router_enabled=False → should_route_via_router returns False."""
        settings = Settings(llm_router_enabled=False)
        assert should_route_via_router(settings) is False

    def test_router_enabled_uses_router_create_llm(self):
        """Test llm_router_enabled=True → should_route_via_router returns True."""
        settings = Settings(llm_router_enabled=True, llm_router_traffic_percent=100)
        assert should_route_via_router(settings) is True

    def test_traffic_percent_0_means_disabled(self):
        """Test llm_router_traffic_percent=0 → should_route_via_router returns False."""
        settings = Settings(llm_router_enabled=True, llm_router_traffic_percent=0)
        assert should_route_via_router(settings) is False

    def test_traffic_percent_100_means_full_cutover(self):
        """Test llm_router_traffic_percent=100 → should_route_via_router always True."""
        settings = Settings(llm_router_enabled=True, llm_router_traffic_percent=100)
        assert should_route_via_router(settings) is True
        # Test multiple calls to ensure consistency
        for _ in range(5):
            assert should_route_via_router(settings) is True

    def test_router_flags_defaults(self):
        """Test default values for router flags."""
        settings = Settings()
        assert settings.llm_router_enabled is False
        assert settings.llm_router_traffic_percent == 0
        assert settings.llm_router_shadow_mode is True

    def test_traffic_percent_out_of_range_raises(self):
        """Test llm_router_traffic_percent out of range raises ValidationError."""
        import pytest
        with pytest.raises(ValueError, match="LLM_ROUTER_TRAFFIC_PERCENT must be 0-100"):
            Settings(llm_router_traffic_percent=101)
        with pytest.raises(ValueError, match="LLM_ROUTER_TRAFFIC_PERCENT must be 0-100"):
            Settings(llm_router_traffic_percent=-1)

    def test_shadow_mode_with_no_writer_logs_info(self):
        """Test route_shadow falls back to logger.info when no operational writer."""
        settings = Settings()
        router = get_llm_router()
        
        # No operational writer
        with patch('llm_client.observability.operational_writer.get_operational_writer', return_value=None):
            with patch('llm_client.agent.router.logger') as mock_logger:
                asyncio.run(router.route_shadow(policy=RoutingPolicy.QUALITY))
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args[0][0]
                assert "SHADOW_MODE:" in call_args

    def test_should_route_via_router_random_behavior(self):
        """Test random behavior for traffic percent between 0 and 100."""
        settings = Settings(llm_router_enabled=True, llm_router_traffic_percent=50)
        
        # Mock random to control behavior
        with patch('random.random', return_value=0.3):
            assert should_route_via_router(settings) is True
        with patch('random.random', return_value=0.7):
            assert should_route_via_router(settings) is False

    def test_should_route_via_router_disabled_policy(self):
        """Test disabled router always returns False."""
        settings = Settings(llm_router_enabled=False, llm_router_traffic_percent=100)
        assert should_route_via_router(settings) is False

    def test_should_route_via_router_zero_traffic(self):
        """Test zero traffic percent always returns False."""
        settings = Settings(llm_router_enabled=True, llm_router_traffic_percent=0)
        assert should_route_via_router(settings) is False

    def test_should_route_via_router_full_traffic(self):
        """Test full traffic percent always returns True."""
        settings = Settings(llm_router_enabled=True, llm_router_traffic_percent=100)
        assert should_route_via_router(settings) is True


class TestRoutingDecisionSerialization:
    """Test RoutingDecision can be serialized for shadow logging."""

    def test_routing_decision_asdict(self):
        """Test RoutingDecision serializes correctly."""
        decision = RoutingDecision(
            provider="openai",
            model="gpt-4o-mini",
            policy=RoutingPolicy.COST,
            reason="Test reason",
            budget_ratio_at_decision=0.5,
            circuit_breaker_active=False,
        )
        # Test asdict (used in shadow logging)
        from dataclasses import asdict
        data = asdict(decision)
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o-mini"
        assert data["policy"] == "cost_priority"  # Enum serialized as string
        assert data["reason"] == "Test reason"
        assert data["budget_ratio_at_decision"] == 0.5
        assert data["circuit_breaker_active"] is False

    def test_routing_decision_json_serializable(self):
        """Test RoutingDecision can be JSON-serialized."""
        decision = RoutingDecision(
            provider="anthropic",
            model="claude-3-haiku",
            policy=RoutingPolicy.PRIVACY,
            reason="Privacy required",
            budget_ratio_at_decision=0.8,
            circuit_breaker_active=True,
        )
        import json
        from dataclasses import asdict
        data = asdict(decision)
        json_str = json.dumps(data)
        assert "anthropic" in json_str
        assert "claude-3-haiku" in json_str
        assert "privacy_priority" in json_str
        assert "Privacy required" in json_str
