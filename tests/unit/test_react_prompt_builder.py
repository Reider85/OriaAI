"""Unit tests for ReactToolCallPromptBuilder (ADR-016 Phase 3, D-4)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from langchain_core.tools import tool

from llm_client.agent.react_prompt_builder import (
    PROMPT_VARIANTS,
    ReactToolCallPromptBuilder,
    get_react_prompt_builder,
)
from llm_client.agent.tool_calling_adapter import ToolCallingAdapter


@tool
def web_search(query: str) -> str:
    """Search the web for information."""
    return f"results for {query}"


@tool
def rag_query(query: str) -> str:
    """Query the RAG system for information."""
    return f"rag results for {query}"


class TestBuildPrompt:
    """Test prompt construction for each variant."""

    def test_build_prompt_v1_strict_contains_tool_name(self):
        builder = ReactToolCallPromptBuilder("v1_strict")
        prompt = builder.build_prompt([web_search, rag_query])
        assert "web_search" in prompt
        assert "rag_query" in prompt

    def test_build_prompt_v2_tolerant_mentions_markdown_fences(self):
        builder = ReactToolCallPromptBuilder("v2_tolerant")
        prompt = builder.build_prompt([web_search])
        assert "```json" in prompt

    def test_build_prompt_v3_cot_mentions_step_by_step(self):
        builder = ReactToolCallPromptBuilder("v3_cot")
        prompt = builder.build_prompt([web_search])
        assert "step by step" in prompt

    def test_format_tool_descriptions_includes_description(self):
        builder = ReactToolCallPromptBuilder("v1_strict")
        prompt = builder.build_prompt([web_search])
        assert "Search the web for information" in prompt

    def test_format_tool_schemas_serializes_args_schema(self):
        builder = ReactToolCallPromptBuilder("v1_strict")
        prompt = builder.build_prompt([rag_query])
        assert '"query"' in prompt
        assert '"properties"' in prompt

    def test_format_tool_schemas_handles_missing_schema(self):
        builder = ReactToolCallPromptBuilder("v1_strict")
        plain_tool = SimpleNamespace(name="plain_tool", description="Plain tool")
        prompt = builder.build_prompt([plain_tool])  # type: ignore[list-item]
        assert "plain_tool: (no schema)" in prompt

    def test_format_tool_schemas_handles_serialization_error(self):
        builder = ReactToolCallPromptBuilder("v1_strict")

        class BrokenSchema:
            @classmethod
            def model_json_schema(cls) -> dict:
                raise RuntimeError("boom")

        broken_tool = SimpleNamespace(
            name="broken_tool",
            description="Tool with broken schema",
            args_schema=BrokenSchema,
        )
        prompt = builder.build_prompt([broken_tool])  # type: ignore[list-item]
        assert "broken_tool: (schema serialization failed)" in prompt

    def test_variant_reports_configured_variant(self):
        assert ReactToolCallPromptBuilder("v3_cot").variant() == "v3_cot"
        assert ReactToolCallPromptBuilder().variant() == "v1_strict"


class TestAdapterDelegation:
    """Test ToolCallingAdapter.build_react_system_prompt delegation."""

    def test_adapter_delegates_to_builder_default_variant(self):
        adapter = ToolCallingAdapter()
        prompt = adapter.build_react_system_prompt([web_search, rag_query])
        assert "EXACTLY this JSON format" in prompt
        assert "web_search" in prompt
        assert "rag_query" in prompt

    def test_adapter_respects_react_prompt_variant_env(self, monkeypatch):
        monkeypatch.setenv("REACT_PROMPT_VARIANT", "v2_tolerant")
        adapter = ToolCallingAdapter()
        prompt = adapter.build_react_system_prompt([web_search])
        assert "```json" in prompt
        assert "EXACTLY this JSON format" not in prompt

    def test_adapter_falls_back_to_v1_on_unknown_variant(self, monkeypatch, caplog):
        monkeypatch.setenv("REACT_PROMPT_VARIANT", "bogus_variant")
        adapter = ToolCallingAdapter()
        with caplog.at_level(logging.WARNING, logger="llm_client.agent.react_prompt_builder"):
            prompt = adapter.build_react_system_prompt([web_search])
        assert "EXACTLY this JSON format" in prompt
        assert any("REACT_PROMPT_VARIANT" in record.getMessage() for record in caplog.records)


class TestGetReactPromptBuilder:
    """Test singleton factory."""

    def test_factory_returns_same_instance_for_same_variant(self):
        first = get_react_prompt_builder("v1_strict")
        second = get_react_prompt_builder("v1_strict")
        assert first is second

    def test_factory_recreates_on_variant_change(self):
        first = get_react_prompt_builder("v1_strict")
        second = get_react_prompt_builder("v3_cot")
        assert first is not second
        assert second.variant() == "v3_cot"
        assert get_react_prompt_builder("v1_strict") is not second

    def test_factory_default_variant_matches_constant(self):
        builder = get_react_prompt_builder("v1_strict")
        assert builder.variant() in PROMPT_VARIANTS
