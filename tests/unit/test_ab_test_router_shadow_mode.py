"""Unit tests for ADR-015 router shadow-mode pilot test (E-2)."""

import pytest

from scripts.ab_test_router_shadow_mode import (
    COST_OVERRUN_TOLERANCE,
    COST_PREDICTABILITY_THRESHOLD,
    ShadowModeResult,
    run_shadow_mode,
)

pytestmark = pytest.mark.eval


def _result_from_ratios(ratios: list[float], base: float = 1.0) -> ShadowModeResult:
    """Build a ShadowModeResult whose (actual - predicted)/pred ratios match."""
    predicted = [base] * len(ratios)
    actual = [base * (1 + r) for r in ratios]
    return ShadowModeResult(
        total_requests=len(ratios),
        router_predicted_costs=predicted,
        actual_costs=actual,
        switching_decisions_logged=len(ratios),
        cost_overrun_count=0,
    )


class TestShadowModeResultPilotCriteria:
    """Pilot criteria logic (ROADMAP §14.1 — ADR-015)."""

    def test_shadow_mode_result_predictability_under_10pct(self):
        """Ratios [0.05, -0.03, 0.04, -0.02] -> stdev <0.10 -> pass."""
        result = _result_from_ratios([0.05, -0.03, 0.04, -0.02])

        assert result.cost_predictability() < COST_PREDICTABILITY_THRESHOLD
        assert result.pilot_pass() is True

    def test_shadow_mode_result_overrun_rate_under_20pct(self):
        """10/100 overruns -> 10% <20% -> pass."""
        result = ShadowModeResult(
            total_requests=100,
            router_predicted_costs=[1.0] * 100,
            actual_costs=[1.0] * 100,
            switching_decisions_logged=100,
            cost_overrun_count=10,
        )

        assert result.cost_overrun_rate() == 0.10
        assert result.cost_overrun_rate() <= COST_OVERRUN_TOLERANCE
        assert result.pilot_pass() is True
        assert result.rollback_required() is False

    def test_shadow_mode_result_rollback_when_overrun_25pct(self):
        """25/100 overruns -> 25% >20% -> rollback."""
        result = ShadowModeResult(
            total_requests=100,
            router_predicted_costs=[1.0] * 100,
            actual_costs=[1.0] * 100,
            switching_decisions_logged=100,
            cost_overrun_count=25,
        )

        assert result.cost_overrun_rate() == 0.25
        assert result.rollback_required() is True
        assert result.pilot_pass() is False

    def test_shadow_mode_result_all_decisions_logged(self):
        """100/100 decisions logged -> pass."""
        result = ShadowModeResult(
            total_requests=100,
            router_predicted_costs=[1.0] * 100,
            actual_costs=[1.0] * 100,
            switching_decisions_logged=100,
            cost_overrun_count=0,
        )

        assert result.pilot_pass() is True

    def test_shadow_mode_result_missing_logged_decision_fails(self):
        """99/100 decisions logged -> pilot_pass fails (logging criterion)."""
        result = ShadowModeResult(
            total_requests=100,
            router_predicted_costs=[1.0] * 100,
            actual_costs=[1.0] * 100,
            switching_decisions_logged=99,
            cost_overrun_count=0,
        )

        assert result.pilot_pass() is False
        assert result.rollback_required() is False


class TestShadowModeResultEdgeCases:
    """Edge cases for ShadowModeResult calculations."""

    def test_shadow_mode_result_zero_requests(self):
        """Zero requests: no division by zero, no rollback."""
        result = ShadowModeResult(
            total_requests=0,
            router_predicted_costs=[],
            actual_costs=[],
            switching_decisions_logged=0,
            cost_overrun_count=0,
        )

        assert result.cost_predictability() == 0.0
        assert result.cost_overrun_rate() == 0.0
        assert result.rollback_required() is False

    def test_shadow_mode_result_predictability_skips_zero_predicted(self):
        """Requests with predicted cost 0 are excluded from the stdev ratio."""
        result = ShadowModeResult(
            total_requests=3,
            router_predicted_costs=[0.0, 1.0, 1.0],
            actual_costs=[0.5, 1.02, 0.99],
            switching_decisions_logged=3,
            cost_overrun_count=1,
        )

        # Only two usable ratios: 0.02 and -0.01 -> stdev <0.10
        assert result.cost_predictability() < COST_PREDICTABILITY_THRESHOLD


class TestRunShadowModeOffline:
    """Offline smoke tests for run_shadow_mode (no network, no API spend)."""

    @pytest.mark.asyncio
    async def test_run_shadow_mode_offline_smoke(self):
        """Offline run executes max_requests requests and logs all decisions."""
        result = await run_shadow_mode(
            duration_minutes=0, max_requests=3, offline=True, interval_seconds=0
        )

        assert result.total_requests == 3
        assert len(result.router_predicted_costs) == 3
        assert len(result.actual_costs) == 3
        assert result.switching_decisions_logged == 3

    @pytest.mark.asyncio
    async def test_run_shadow_mode_offline_zero_prediction_excluded(self):
        """Offline: COST policy routes to a free model (predicted == 0.0);
        zero predictions are excluded from overrun accounting."""
        result = await run_shadow_mode(
            duration_minutes=0, max_requests=5, offline=True, interval_seconds=0
        )

        # predicted == actual for every request (cost table, same model)
        assert result.cost_predictability() == 0.0
        assert result.cost_overrun_count == 0
        assert result.pilot_pass() is True
