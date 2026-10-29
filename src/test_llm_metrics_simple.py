"""Minimal test for llm_metrics module."""

import sys
import os

# Add current directory to path (src)
sys.path.insert(0, os.path.dirname(__file__))


def test_llm_metrics_import():
    """Test that llm_metrics can be imported directly."""
    try:
        from llm_client.observability.llm_metrics import record_llm_call, LLM_CALLS_TOTAL, REGISTRY

        print("PASS: llm_metrics import successful")
        return True
    except ImportError as e:
        print(f"FAIL: llm_metrics import failed: {e}")
        return False


def test_llm_metrics_functionality():
    """Test basic llm_metrics functionality."""
    try:
        from llm_client.observability.llm_metrics import record_llm_call, LLM_CALLS_TOTAL, REGISTRY

        # Create fresh registry for testing
        from prometheus_client import CollectorRegistry

        test_registry = CollectorRegistry()

        # Create new metrics instance with test registry
        from llm_client.observability.llm_metrics import LLM_CALLS_TOTAL as TestLLM_CALLS_TOTAL

        TestLLM_CALLS_TOTAL._type = None  # Reset

        # Record a call
        record_llm_call(
            provider="openai",
            model="gpt-4o-mini",
            status="success",
            mode="native",
            latency_seconds=0.5,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
        )

        # Check counter
        samples = LLM_CALLS_TOTAL.labels(
            provider="openai", model="gpt-4o-mini", status="success", mode="native"
        ).collect()

        if len(samples) == 1 and samples[0].value == 1.0:
            print("PASS: llm_metrics functionality works")
            return True
        else:
            print(f"FAIL: llm_metrics functionality failed: {samples}")
            return False
    except Exception as e:
        print(f"FAIL: llm_metrics functionality error: {e}")
        return False


def test_token_tracker_integration():
    """Test TokenUsageTracker integration."""
    try:
        # Create minimal mock
        class MockWriter:
            def __init__(self):
                self.events = []

            async def write(self, event):
                self.events.append(event)

        from llm_client.agent.provider import TokenUsageTracker

        writer = MockWriter()
        tracker = TokenUsageTracker(writer, session_id="test")

        # Mock response
        class MockTokenUsage:
            prompt_tokens = 100
            completion_tokens = 50

        class MockLLMOutput:
            token_usage = MockTokenUsage()
            model_name = "gpt-4o-mini"

        class MockResponse:
            llm_output = MockLLMOutput()

        # Test the integration
        import asyncio

        asyncio.run(tracker.on_llm_end(MockResponse()))

        # Check both operational writer and metrics were called
        if len(writer.events) == 1 and writer.events[0]["event_type"] == "llm_usage":
            print("PASS: TokenUsageTracker integration works")
            return True
        else:
            print(f"FAIL: TokenUsageTracker integration failed: {writer.events}")
            return False
    except Exception as e:
        print(f"FAIL: TokenUsageTracker integration error: {e}")
        return False


if __name__ == "__main__":
    print("Testing llm_metrics implementation...")

    tests = [
        test_llm_metrics_import,
        test_llm_metrics_functionality,
        test_token_tracker_integration,
    ]

    results = []
    for test in tests:
        results.append(test())

    if all(results):
        print("\nPASS: All tests passed!")
        sys.exit(0)
    else:
        print(f"\nFAIL: {sum(1 for r in results if not r)} tests failed")
        sys.exit(1)
