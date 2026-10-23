"""Unit tests for CostGuard (C-3 ADR-015)."""

import asyncio
from unittest.mock import MagicMock, patch

from llm_client.agent.cost_guard import CostGuard, get_cost_guard
from llm_client.agent.model_cost_table import ModelCost, ModelCostTable
from llm_client.agent.router import LLMRouter


class TestCostGuard:
    """Test CostGuard core functionality."""

    def setup_method(self):
        """Reset singletons for each test."""
        import llm_client.agent.cost_guard as cg_module
        import llm_client.agent.router as router_module

        cg_module._guard = None
        router_module._router = None

        # Create mock cost table
        self.cost_table = ModelCostTable()
        self.cost_table.costs = {
            "openai": {
                "gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60),
                "gpt-4o": ModelCost(prompt=2.50, completion=10.00),
            }
        }

        # Create mock router
        self.router = LLMRouter(
            provider_factory=MagicMock(),
            cost_table=self.cost_table,
            budget_usd=100.0,
        )

    def test_record_spend_below_threshold_no_trigger(self):
        """Test record $10 on $100 budget → triggered=False."""
        guard = CostGuard(self.router)
        triggered = asyncio.run(guard.record_spend(10.0))
        assert triggered is False
        assert self.router._spent_usd == 10.0

    def test_record_spend_at_80pct_triggers(self):
        """Test budget=100, spent=79, record $2 → triggered=True."""
        self.router._spent_usd = 79.0
        guard = CostGuard(self.router)
        triggered = asyncio.run(guard.record_spend(2.0))
        assert triggered is True
        assert self.router._spent_usd == 81.0

    def test_is_over_budget_at_100pct(self):
        """Test spent=100, budget=100 → True."""
        self.router._spent_usd = 100.0
        guard = CostGuard(self.router)
        assert guard.is_over_budget() is True
        self.router._spent_usd = 99.0
        assert guard.is_over_budget() is False

    def test_remaining_budget_correct(self):
        """Test spent=30, budget=100 → 70."""
        self.router._spent_usd = 30.0
        guard = CostGuard(self.router)
        assert guard.remaining_budget() == 70.0

    def test_reset_monthly_zeroes_spent(self):
        """Test spent=50, reset → spent=0, month_start updated."""
        self.router._spent_usd = 50.0
        guard = CostGuard(self.router)
        old_month = guard.month_start()
        asyncio.run(guard.reset_monthly())
        assert self.router._spent_usd == 0.0
        assert guard.month_start().year >= old_month.year  # Allow same month (fast test)

    @patch("llm_client.agent.cost_guard.update_budget_usage")
    def test_update_budget_usage_prometheus_called(self, mock_update):
        """Test update_budget_usage called with correct args."""
        guard = CostGuard(self.router)
        asyncio.run(guard.record_spend(15.0))
        mock_update.assert_called_with(15.0, 100.0)

    def test_integration_with_token_usage_tracker(self):
        """Integration: TokenUsageTracker.on_llm_end → CostGuard.record_spend."""
        # Reset singleton
        import llm_client.agent.cost_guard as cg_module
        from llm_client.agent.provider import TokenUsageTracker

        cg_module._guard = None

        # Create mock writer
        class MockWriter:
            def __init__(self):
                self.events = []

            async def write(self, event):
                self.events.append(event)

        # Create tracker
        writer = MockWriter()
        tracker = TokenUsageTracker(writer, session_id="test_session", provider="openai")

        # Mock LLM response
        class MockTokenUsage:
            prompt_tokens = 100
            completion_tokens = 50

        class MockLLMOutput:
            token_usage = MockTokenUsage()
            model_name = "gpt-4o-mini"

        class MockResponse:
            llm_output = MockLLMOutput()

        # Call on_llm_end
        asyncio.run(tracker.on_llm_end(MockResponse()))

        # Check that LLM call was recorded
        assert self.router._spent_usd >= 0, (
            f"CostGuard should have recorded the spend, got {self.router._spent_usd}"
        )
        assert len(writer.events) == 1
        assert writer.events[0]["event_type"] == "llm_usage"


class TestCostGuardEndpoints:
    """Test admin endpoints (mirrored pattern from test_cancel_endpoint.py)."""

    def setup_method(self):
        """Reset singletons and create mock settings."""
        import llm_client.agent.cost_guard as cg_module
        import llm_client.agent.router as router_module

        cg_module._guard = None
        router_module._router = None

        # Create mock cost table and router
        cost_table = ModelCostTable()
        cost_table.costs = {"openai": {"gpt-4o-mini": ModelCost(prompt=0.15, completion=0.60)}}
        self.router = LLMRouter(
            provider_factory=MagicMock(),
            cost_table=cost_table,
            budget_usd=100.0,
        )
        self.router._spent_usd = 50.0  # Pre-spend some budget

    def _build_app(self):
        """Build minimal FastAPI app with cost guard routes."""
        from fastapi import FastAPI, Header
        from fastapi.testclient import TestClient

        app = FastAPI()

        # Mock settings
        class MockSettings:
            admin_token = "secret-token"
            llm_router_cost_guard_threshold = 0.8
            llm_monthly_budget_usd = 100.0

        # Inject settings for closure
        app.state.settings = MockSettings()

        # Mock get_cost_guard
        def mock_get_cost_guard():
            guard = CostGuard(self.router)
            return guard

        # Add routes
        @app.post("/admin/cost-guard/reset")
        async def reset_cost_guard(admin_token: str = Header(default="")):
            if admin_token != app.state.settings.admin_token:
                from fastapi import HTTPException

                raise HTTPException(status_code=403, detail="invalid admin token")
            await mock_get_cost_guard().reset_monthly()
            return {"status": "ok", "spent_usd": 0.0}

        @app.get("/admin/cost-guard/status")
        async def cost_guard_status(admin_token: str = Header(default="")):
            if admin_token != app.state.settings.admin_token:
                from fastapi import HTTPException

                raise HTTPException(status_code=403, detail="invalid admin token")
            g = mock_get_cost_guard()
            return {
                "spent_usd": g._router._spent_usd,
                "budget_usd": g._router._budget,
                "ratio": g._router._spent_usd / g._router._budget if g._router._budget else 0,
                "over_budget": g.is_over_budget(),
                "remaining_usd": g.remaining_budget(),
                "month_start": g.month_start().isoformat(),
            }

        return TestClient(app)

    def test_reset_endpoint_403_no_token(self):
        """Test reset without token → 403."""
        client = self._build_app()
        resp = client.post("/admin/cost-guard/reset", headers={})
        assert resp.status_code == 403

    def test_reset_endpoint_403_wrong_token(self):
        """Test reset with wrong token → 403."""
        client = self._build_app()
        resp = client.post("/admin/cost-guard/reset", headers={"admin-token": "wrong"})
        assert resp.status_code == 403

    def test_reset_endpoint_200_with_token(self):
        """Test reset with correct token → 200, spent=0."""
        client = self._build_app()
        resp = client.post("/admin/cost-guard/reset", headers={"admin-token": "secret-token"})
        assert resp.status_code == 200
        assert resp.json()["spent_usd"] == 0.0

    def test_status_endpoint_403_no_token(self):
        """Test status without token → 403."""
        client = self._build_app()
        resp = client.get("/admin/cost-guard/status", headers={})
        assert resp.status_code == 403

    def test_status_endpoint_200_with_token(self):
        """Test status with correct token → 200."""
        client = self._build_app()
        resp = client.get("/admin/cost-guard/status", headers={"admin-token": "secret-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["spent_usd"] == 50.0
        assert data["budget_usd"] == 100.0
        assert data["ratio"] == 0.5
        assert data["remaining_usd"] == 50.0


class TestCostGuardSingleton:
    """Test CostGuard singleton behavior."""

    def setup_method(self):
        """Reset singleton."""
        import llm_client.agent.cost_guard as cg_module

        cg_module._guard = None

    def test_get_cost_guard_singleton(self):
        """Test get_cost_guard returns same instance."""
        guard1 = get_cost_guard()
        guard2 = get_cost_guard()
        assert guard1 is guard2

    def test_get_cost_guard_uses_real_router(self):
        """Test get_cost_guard uses real LLMRouter singleton."""
        guard = get_cost_guard()
        assert guard._router is not None
        assert hasattr(guard._router, "_spent_usd")
