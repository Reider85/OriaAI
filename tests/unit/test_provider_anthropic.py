"""Tests for Phase 3 ADR-015 Anthropic provider implementation."""

import pytest
from langchain_anthropic import ChatAnthropic

from llm_client.agent.provider import LLMProviderFactory


class TestAnthropicProvider:
    def test_create_anthropic_returns_chat_anthropic(self):
        llm = LLMProviderFactory.create("anthropic", "claude-3-haiku", api_key="sk-ant-test")
        assert isinstance(llm, ChatAnthropic)
        assert llm.model == "claude-3-haiku"

    def test_create_anthropic_uppercase_normalized(self):
        llm = LLMProviderFactory.create("ANTHROPIC", "claude-3-haiku", api_key="sk-ant-test")
        assert isinstance(llm, ChatAnthropic)
        assert llm.model == "claude-3-haiku"

    def test_create_anthropic_uses_max_tokens(self):
        from llm_client.config import settings

        original_max_tokens = settings.anthropic_max_tokens
        try:
            settings.anthropic_max_tokens = 1024
            llm = LLMProviderFactory.create("anthropic", "claude-3-haiku", api_key="sk-ant-test")
            assert llm.max_tokens == 1024
        finally:
            settings.anthropic_max_tokens = original_max_tokens

    def test_create_anthropic_max_tokens_override_via_kwargs(self):
        from llm_client.config import settings

        original_max_tokens = settings.anthropic_max_tokens
        try:
            settings.anthropic_max_tokens = 1024
            llm = LLMProviderFactory.create(
                "anthropic", "claude-3-haiku", api_key="sk-ant-test", max_tokens=2048
            )
            assert llm.max_tokens == 2048
        finally:
            settings.anthropic_max_tokens = original_max_tokens

    def test_create_anthropic_with_streaming_true(self):
        llm = LLMProviderFactory.create(
            "anthropic", "claude-3-haiku", api_key="sk-ant-test", streaming=True
        )
        assert llm.streaming is True

    def test_create_anthropic_with_temperature(self):
        llm = LLMProviderFactory.create(
            "anthropic", "claude-3-haiku", api_key="sk-ant-test", temperature=0.2
        )
        assert llm.temperature == 0.2

    def test_anthropic_model_default_matches_settings(self):
        from llm_client.config import settings

        llm = LLMProviderFactory.create(
            "anthropic", settings.anthropic_model, api_key="sk-ant-test"
        )
        assert llm.model == settings.anthropic_model
