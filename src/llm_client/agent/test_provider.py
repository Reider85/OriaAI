"""Tests for AG-2 LLMProviderFactory, TokenUsageTracker, and retry decorator."""

from typing import ClassVar

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from llm_client.agent.provider import (
    LLMProviderFactory,
    TokenUsageTracker,
    create_retry_decorator,
)
from llm_client.config import Settings

# ── LLMProviderFactory tests ──────────────────────────────────────────────────


class TestLLMProviderFactory:
    def test_create_openai_returns_chat_openai(self):
        llm = LLMProviderFactory.create("openai", "gpt-4o-mini", api_key="sk-test")
        assert isinstance(llm, ChatOpenAI)
        assert isinstance(llm, BaseChatModel)
        assert llm.model_name == "gpt-4o-mini"

    def test_create_openai_streaming_enabled(self):
        llm = LLMProviderFactory.create(
            "openai", "gpt-4o-mini", api_key="sk-test", streaming=True
        )
        assert llm.streaming is True

    def test_create_openai_streaming_disabled(self):
        llm = LLMProviderFactory.create(
            "openai", "gpt-4o-mini", api_key="sk-test", streaming=False
        )
        assert llm.streaming is False

    def test_create_anthropic_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="Phase 3.*ADR-015"):
            LLMProviderFactory.create("anthropic", "claude-3-5-sonnet-20241022")

    def test_create_ollama_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="Phase 4.*ADR-016"):
            LLMProviderFactory.create("ollama", "llama3.1")

    def test_create_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMProviderFactory.create("google", "gemini-pro")


# ── Settings validation tests ─────────────────────────────────────────────────


class TestSettingsValidation:
    def test_empty_openai_key_with_openai_provider_fails(self):
        with pytest.raises(ValidationError, match="OPENAI_API_KEY required"):
            Settings(
                openai_api_key="",
                llm_provider="openai",
                environment="dev",
                operational_log_sink="stdout",
                kms_provider="vault",
            )

    def test_valid_openai_settings_passes(self):
        s = Settings(
            openai_api_key="sk-test-key",
            llm_provider="openai",
            environment="dev",
            operational_log_sink="stdout",
            kms_provider="vault",
        )
        assert s.llm_provider == "openai"
        assert s.openai_api_key == "sk-test-key"
        assert s.openai_model == "gpt-4o-mini"

    def test_invalid_llm_provider_fails(self):
        with pytest.raises(ValidationError, match="LLM_PROVIDER must be"):
            Settings(
                llm_provider="google",
                environment="dev",
                operational_log_sink="stdout",
                kms_provider="vault",
            )

    def test_anthropic_provider_does_not_validate_key(self):
        # Phase 1: anthropic provider is not implemented, but key validation is skipped
        s = Settings(
            llm_provider="anthropic",
            anthropic_api_key="",
            environment="dev",
            operational_log_sink="stdout",
            kms_provider="vault",
        )
        assert s.llm_provider == "anthropic"


# ── TokenUsageTracker tests ───────────────────────────────────────────────────


class TestTokenUsageTracker:
    @pytest.mark.asyncio
    async def test_on_llm_end_writes_usage_event(self):
        class MockWriter:
            def __init__(self):
                self.events = []

            async def write(self, event):
                self.events.append(event)

        writer = MockWriter()
        tracker = TokenUsageTracker(writer, session_id="s1")

        # Simulate LLM response with token usage
        class MockTokenUsage:
            prompt_tokens = 100
            completion_tokens = 50

        class MockLLMOutput:
            token_usage = MockTokenUsage()
            model_name = "gpt-4o-mini"

        class MockResponse:
            llm_output = MockLLMOutput()

        await tracker.on_llm_end(MockResponse())

        assert len(writer.events) == 1
        event = writer.events[0]
        assert event["event_type"] == "llm_usage"
        assert event["provider"] == "openai"
        assert event["model"] == "gpt-4o-mini"
        assert event["prompt_tokens"] == 100
        assert event["completion_tokens"] == 50
        assert event["session_id"] == "s1"
        assert event["cost_estimate_usd"] > 0

    @pytest.mark.asyncio
    async def test_on_llm_end_handles_missing_usage(self):
        class MockWriter:
            def __init__(self):
                self.events = []

            async def write(self, event):
                self.events.append(event)

        writer = MockWriter()
        tracker = TokenUsageTracker(writer, session_id="s2")

        class MockResponse:
            llm_output = None

        await tracker.on_llm_end(MockResponse())

        assert len(writer.events) == 1
        event = writer.events[0]
        assert event["prompt_tokens"] == 0
        assert event["completion_tokens"] == 0

    @pytest.mark.asyncio
    async def test_on_llm_end_writer_exception_does_not_raise(self):
        class FailingWriter:
            async def write(self, event):
                raise RuntimeError("write failed")

        tracker = TokenUsageTracker(FailingWriter(), session_id="s3")

        class MockResponse:
            llm_output: ClassVar[dict] = {"token_usage": None, "model_name": "gpt-4o"}

        # Should not raise
        await tracker.on_llm_end(MockResponse())


# ── Cost estimation tests ─────────────────────────────────────────────────────


class TestCostEstimation:
    def test_known_model_cost(self):
        from llm_client.agent.provider import _estimate_cost

        cost = _estimate_cost("gpt-4o-mini", 1000, 500)
        # gpt-4o-mini: input $0.15/1M, output $0.60/1M
        expected = (1000 * 0.15 + 500 * 0.60) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_unknown_model_cost_zero(self):
        from llm_client.agent.provider import _estimate_cost

        cost = _estimate_cost("unknown-model", 1000, 500)
        assert cost == 0.0


# ── Retry decorator tests ─────────────────────────────────────────────────────


class TestRetryDecorator:
    def test_retry_decorator_is_callable(self):
        decorator = create_retry_decorator(max_retries=2)
        assert callable(decorator)

    def test_retry_decorator_wraps_function(self):
        decorator = create_retry_decorator(max_retries=2)

        @decorator
        def sample_func():
            return "ok"

        assert sample_func() == "ok"
