"""Unit tests for RouterMetricsLogger (C-7 ADR-015)."""


from unittest.mock import AsyncMock, MagicMock, patch

from llm_client.agent.router import RoutingDecision, RoutingPolicy
from llm_client.observability.router_metrics_logger import get_router_metrics_logger


class TestRouterMetricsLogger:
    """Test RouterMetricsLogger logging behavior."""

    def setup_method(self):
        """Reset singleton for each test."""
        import llm_client.observability.router_metrics_logger as logger_module
        logger_module._logger = None

    @patch("llm_client.observability.router_metrics_logger.get_operational_writer")
    async def test_log_decision_writes_to_operational_stream(self, mock_get_writer):
        """Test log_decision writes router_decision event to operational stream."""
        mock_writer = AsyncMock()
        mock_get_writer.return_value = mock_writer

        logger = get_router_metrics_logger()
        decision = RoutingDecision(
            provider="openai",
            model="gpt-4o-mini",
            policy=RoutingPolicy.COST,
            reason="Cost test",
            budget_ratio_at_decision=0.5,
            circuit_breaker_active=False,
        )
        await logger.log_decision(decision, request_id="req123")

        mock_writer.write.assert_called_once()
        call_args = mock_writer.write.call_args[0][0]
        assert call_args["event_type"] == "router_decision"
        assert call_args["request_id"] == "req123"
        assert call_args["provider"] == "openai"
        assert call_args["model"] == "gpt-4o-mini"
        assert call_args["policy"] == "cost_priority"
        assert call_args["reason"] == "Cost test"
        assert call_args["budget_ratio"] == 0.5
        assert call_args["circuit_breaker_active"] is False

    @patch("llm_client.observability.router_metrics_logger.get_operational_writer")
    async def test_log_decision_includes_all_fields(self, mock_get_writer):
        """Test log_decision event has all required fields."""
        mock_writer = AsyncMock()
        mock_get_writer.return_value = mock_writer

        logger = get_router_metrics_logger()
        decision = RoutingDecision(
            provider="anthropic",
            model="claude-3-haiku",
            policy=RoutingPolicy.QUALITY,
            reason="Quality priority — gpt-4o",
            budget_ratio_at_decision=0.8,
            circuit_breaker_active=True,
        )
        await logger.log_decision(decision, request_id="req456")

        event = mock_writer.write.call_args[0][0]
        assert "event_type" in event
        assert "timestamp" in event
        assert "request_id" in event
        assert "provider" in event
        assert "model" in event
        assert "policy" in event
        assert "reason" in event
        assert "budget_ratio" in event
        assert "circuit_breaker_active" in event

    @patch("llm_client.observability.router_metrics_logger.get_operational_writer")
    async def test_log_shadow_decision_with_match(self, mock_get_writer):
        """Test log_shadow_decision with match=True."""
        mock_writer = AsyncMock()
        mock_get_writer.return_value = mock_writer

        logger = get_router_metrics_logger()
        decision = RoutingDecision(
            provider="openai",
            model="gpt-4o-mini",
            policy=RoutingPolicy.COST,
            reason="Cost test",
            budget_ratio_at_decision=0.5,
            circuit_breaker_active=False,
        )
        await logger.log_shadow_decision(
            decision,
            actual_provider="openai",
            actual_model="gpt-4o-mini",
            request_id="shadow123",
        )

        event = mock_writer.write.call_args[0][0]
        assert event["event_type"] == "router_shadow_comparison"
        assert event["request_id"] == "shadow123"
        assert event["router_would_choose_provider"] == "openai"
        assert event["router_would_choose_model"] == "gpt-4o-mini"
        assert event["actual_provider"] == "openai"
        assert event["actual_model"] == "gpt-4o-mini"
        assert event["match"] is True

    @patch("llm_client.observability.router_metrics_logger.get_operational_writer")
    async def test_log_shadow_decision_with_mismatch(self, mock_get_writer):
        """Test log_shadow_decision with match=False."""
        mock_writer = AsyncMock()
        mock_get_writer.return_value = mock_writer

        logger = get_router_metrics_logger()
        decision = RoutingDecision(
            provider="openai",
            model="gpt-4o-mini",
            policy=RoutingPolicy.COST,
            reason="Cost test",
            budget_ratio_at_decision=0.5,
            circuit_breaker_active=False,
        )
        await logger.log_shadow_decision(
            decision,
            actual_provider="anthropic",
            actual_model="claude-3-haiku",
            request_id="shadow456",
        )

        event = mock_writer.write.call_args[0][0]
        assert event["event_type"] == "router_shadow_comparison"
        assert event["request_id"] == "shadow456"
        assert event["router_would_choose_provider"] == "openai"
        assert event["router_would_choose_model"] == "gpt-4o-mini"
        assert event["actual_provider"] == "anthropic"
        assert event["actual_model"] == "claude-3-haiku"
        assert event["match"] is False

    @patch("llm_client.observability.router_metrics_logger.get_operational_writer")
    async def test_log_decision_increments_prometheus_counter(self, mock_get_writer):
        """Test log_decision increments ROUTER_DECISIONS_TOTAL counter."""
        mock_writer = AsyncMock()
        mock_get_writer.return_value = mock_writer

        from llm_client.observability.llm_metrics import ROUTER_DECISIONS_TOTAL
        # Reset counter
        ROUTER_DECISIONS_TOTAL.clear()

        logger = get_router_metrics_logger()
        decision = RoutingDecision(
            provider="openai",
            model="gpt-4o",
            policy=RoutingPolicy.QUALITY,
            reason="Quality priority",
            budget_ratio_at_decision=0.2,
            circuit_breaker_active=False,
        )
        await logger.log_decision(decision, request_id="counter123")

        # Check counter incremented
        before = sum(TestRouterMetricsLogger._get_counter_values())
        await logger.log_decision(decision, request_id="counter456")
        after = sum(TestRouterMetricsLogger._get_counter_values())
        assert after == before + 1

    @patch("llm_client.observability.router_metrics_logger.get_operational_writer")
    async def test_log_decision_no_writer_falls_back_to_logger(self, mock_get_writer):
        """Test log_decision falls back to logger.info when no operational writer."""
        mock_get_writer.return_value = None
        mock_logger = MagicMock()
        with patch("llm_client.observability.router_metrics_logger.logger", mock_logger):
            logger = get_router_metrics_logger()
            decision = RoutingDecision(
                provider="custom-openai",
                model="default",
                policy=RoutingPolicy.PRIVACY,
                reason="Privacy required",
                budget_ratio_at_decision=0.1,
                circuit_breaker_active=False,
            )
            await logger.log_decision(decision)

            # Check logger.info called
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args[0][0]
            assert "Router decision: provider=" in call_args

    @staticmethod
    def _get_counter_values():
        """Helper to get current counter values for testing."""
        from llm_client.observability.llm_metrics import ROUTER_DECISIONS_TOTAL
        # Prometheus counter: collect() returns a list of Metric objects with samples
        return [m.samples[0].value for m in ROUTER_DECISIONS_TOTAL.collect()]


class TestRouterMetricsLoggerSingleton:
    """Test singleton behavior."""

    def setup_method(self):
        """Reset singleton for each test."""
        import llm_client.observability.router_metrics_logger as logger_module
        logger_module._logger = None

    def test_get_router_metrics_logger_singleton(self):
        """Test get_router_metrics_logger returns same instance."""
        logger1 = get_router_metrics_logger()
        logger2 = get_router_metrics_logger()
        assert logger1 is logger2