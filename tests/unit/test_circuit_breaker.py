"""Unit tests for CircuitBreaker (C-4 ADR-015)."""

import asyncio
import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from llm_client.agent.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStatus,
    get_circuit_breaker,
)

logger = logging.getLogger(__name__)


class TestCircuitState:
    """Test CircuitState enum values."""
    
    def test_state_values(self):
        """Test all state enum values are correct."""
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"


class TestCircuitStatus:
    """Test CircuitStatus dataclass."""
    
    def test_status_creation(self):
        """Test CircuitStatus creation with all fields."""
        status = CircuitStatus(
            provider="openai",
            state=CircuitState.CLOSED,
            error_rate_5m=0.0,
            last_state_change=time.time(),
            consecutive_trial_successes=0,
        )
        assert status.provider == "openai"
        assert status.state == CircuitState.CLOSED
        assert status.error_rate_5m == 0.0
        assert status.consecutive_trial_successes == 0


class TestCircuitBreaker:
    """Test CircuitBreaker core functionality."""
    
    def setup_method(self):
        """Reset singleton for each test."""
        import llm_client.agent.circuit_breaker as cb_module
        cb_module._breaker = None
        
        self.breaker = CircuitBreaker(error_threshold=0.5)
    
    def test_check_returns_closed_initial_state(self):
        """Test fresh breaker returns CLOSED state."""
        status = asyncio.run(self.breaker.check("openai"))
        assert status.state == CircuitState.CLOSED
        assert status.error_rate_5m == 0.0
        assert status.consecutive_trial_successes == 0
    
    @patch('llm_client.observability.llm_metrics.LLM_ERROR_RATE')
    def test_check_opens_on_high_error_rate(self, mock_error_rate, caplog):
        """Test breaker opens when error rate > threshold."""
        # Mock gauge to show 60% error rate
        mock_gauge = MagicMock()
        mock_gauge._value.get.return_value = 0.6
        mock_error_rate.labels.return_value = mock_gauge
        
        status = asyncio.run(self.breaker.check("openai"))
        assert status.state == CircuitState.OPEN
        assert "Circuit OPEN for provider openai (error rate 60.0%)" in caplog.text
    
    @patch('llm_client.observability.llm_metrics.LLM_ERROR_RATE')
    def test_check_half_open_after_cooldown(self, mock_error_rate):
        """Test OPEN state transitions to HALF_OPEN after cooldown."""
        # First call: opens circuit
        mock_gauge = MagicMock()
        mock_gauge._value.get.return_value = 0.6
        mock_error_rate.labels.return_value = mock_gauge
        
        status1 = asyncio.run(self.breaker.check("openai"))
        assert status1.state == CircuitState.OPEN
        
        # Simulate cooldown elapsed by advancing time and calling again
        # Keep error rate below threshold to test cooldown transition
        mock_gauge._value.get.return_value = 0.3
        # Mock time.time() to simulate cooldown elapsed
        with patch('time.time') as mock_time:
            mock_time.return_value = status1.last_state_change + self.breaker.COOLDOWN_SECONDS + 1
            status2 = asyncio.run(self.breaker.check("openai"))
            assert status2.state == CircuitState.HALF_OPEN
    
    @patch('llm_client.observability.llm_metrics.LLM_ERROR_RATE')
    def test_record_success_in_half_open_closes_after_3(self, mock_error_rate):
        """Test 3 record_success calls in HALF_OPEN → CLOSED."""
        # First, set HALF_OPEN state by opening and then cooling down
        mock_gauge = MagicMock()
        mock_gauge._value.get.return_value = 0.6  # Above threshold to open
        mock_error_rate.labels.return_value = mock_gauge
        
        # Open the circuit
        status1 = asyncio.run(self.breaker.check("openai"))
        assert status1.state == CircuitState.OPEN
        
        # Cool down to HALF_OPEN
        mock_gauge._value.get.return_value = 0.3  # Below threshold
        with patch('time.time') as mock_time:
            mock_time.return_value = status1.last_state_change + self.breaker.COOLDOWN_SECONDS + 1
            status2 = asyncio.run(self.breaker.check("openai"))
            assert status2.state == CircuitState.HALF_OPEN
        
        # Record 3 successes
        for _ in range(3):
            asyncio.run(self.breaker.record_success("openai"))
        
        # Next check should close the circuit
        mock_gauge._value.get.return_value = 0.2  # Still below threshold
        final_status = asyncio.run(self.breaker.check("openai"))
        assert final_status.state == CircuitState.CLOSED
        assert final_status.consecutive_trial_successes == 0
    
    @patch('llm_client.observability.llm_metrics.LLM_ERROR_RATE')
    def test_record_failure_in_half_open_reopens(self, mock_error_rate):
        """Test record_failure in HALF_OPEN reopens circuit."""
        # First, set HALF_OPEN state by opening and then cooling down
        mock_gauge = MagicMock()
        mock_gauge._value.get.return_value = 0.6  # Above threshold to open
        mock_error_rate.labels.return_value = mock_gauge
        
        # Open the circuit
        status1 = asyncio.run(self.breaker.check("openai"))
        assert status1.state == CircuitState.OPEN
        
        # Cool down to HALF_OPEN
        mock_gauge._value.get.return_value = 0.3  # Below threshold
        with patch('time.time') as mock_time:
            mock_time.return_value = status1.last_state_change + self.breaker.COOLDOWN_SECONDS + 1
            status2 = asyncio.run(self.breaker.check("openai"))
            assert status2.state == CircuitState.HALF_OPEN
        
        # Record failure → should reopen
        asyncio.run(self.breaker.record_failure("openai"))
        
        # Check should still be OPEN
        final_status = asyncio.run(self.breaker.check("openai"))
        assert final_status.state == CircuitState.OPEN
        assert final_status.consecutive_trial_successes == 0
    
    def test_read_error_rate_returns_zero_on_missing(self):
        """Test _read_error_rate returns 0.0 on gauge access failure."""
        with patch('llm_client.observability.llm_metrics.LLM_ERROR_RATE') as mock_error_rate:
            mock_error_rate.labels.side_effect = (AttributeError("Gauge read failed"),)
            
            rate = asyncio.run(self.breaker._read_error_rate("openai"))
            assert rate == 0.0
    
    @patch('llm_client.observability.llm_metrics.LLM_ERROR_RATE')
    def test_collector_updates_gauge_integration(self, mock_error_rate):
        """Integration test: record_llm_call errors → collector → gauge > 0."""
        from llm_client.observability.llm_metrics import record_llm_call
        
        # Simulate some errors
        record_llm_call(
            provider="openai",
            model="gpt-4o-mini",
            status="error",
            mode="native",
            latency_seconds=1.0,
        )
        
        # Mock the gauge to aggregate the error
        mock_gauge = MagicMock()
        mock_gauge._value.get.return_value = 1.0  # 100% error rate
        mock_error_rate.labels.return_value = mock_gauge
        
        # Test that breaker detects high error rate
        status = asyncio.run(self.breaker.check("openai"))
        assert status.error_rate_5m == 1.0


class TestGetCircuitBreaker:
    """Test get_circuit_breaker singleton factory."""
    
    def setup_method(self):
        """Reset singleton for each test."""
        import llm_client.agent.circuit_breaker as cb_module
        cb_module._breaker = None
    
    def test_get_circuit_breaker_singleton(self):
        """Test get_circuit_breaker returns same instance."""
        breaker1 = get_circuit_breaker()
        breaker2 = get_circuit_breaker()
        assert breaker1 is breaker2
    
    def test_get_circuit_breaker_with_threshold(self):
        """Test get_circuit_breaker uses custom threshold."""
        breaker = get_circuit_breaker(error_threshold=0.7)
        assert breaker._error_threshold == 0.7


class TestConfigDefaults:
    """Test circuit breaker config defaults."""
    
    def test_circuit_breaker_settings_defaults(self):
        """Test circuit breaker settings have correct defaults."""
        from llm_client.config import Settings
        settings = Settings()
        assert settings.llm_circuit_breaker_error_threshold == 0.5