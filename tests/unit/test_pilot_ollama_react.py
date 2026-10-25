"""Unit tests for scripts/pilot_ollama_react.py (ADR-016 pilot, Block D-6)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from scripts.pilot_ollama_react import (
    MIN_SAMPLE_SIZE,
    PilotResult,
    _extract_tool_call,
    run_pilot,
)


def _result(total: int, successes: int, sample_size_warning: bool = False) -> PilotResult:
    return PilotResult(
        total_tests=total,
        successes=successes,
        failures=total - successes,
        success_rate=successes / total if total else 0.0,
        failure_reasons={},
        sample_size_warning=sample_size_warning,
    )


def test_pilot_result_pass_at_80pct() -> None:
    result = _result(total=10, successes=8)
    assert result.pilot_pass() is True
    assert result.verdict() == "pass"
    assert result.rollback_required() is False


def test_pilot_result_rollback_at_50pct() -> None:
    result = _result(total=10, successes=5)
    assert result.rollback_required() is True
    assert result.pilot_pass() is False
    assert result.verdict() == "rollback"


def test_pilot_result_partial_at_70pct() -> None:
    result = _result(total=10, successes=7)
    assert result.pilot_pass() is False
    assert result.rollback_required() is False
    assert result.verdict() == "partial"


def test_pilot_result_sample_size_warning() -> None:
    result = _result(total=5, successes=5, sample_size_warning=True)
    assert result.sample_size_warning is True
    assert result.success_rate == 1.0
    assert result.pilot_pass() is False
    assert MIN_SAMPLE_SIZE == 20


def test_extract_tool_call_normalized_shape() -> None:
    message = AIMessage(
        content="searching",
        tool_calls=[{"name": "web_search", "args": {"query": "q"}, "id": "react_1"}],
    )
    assert _extract_tool_call(message) == {"name": "web_search", "args": {"query": "q"}}


def test_extract_tool_call_openai_additional_kwargs_shape() -> None:
    message = AIMessage(
        content="searching",
        additional_kwargs={
            "tool_calls": [
                {
                    "id": "react_2",
                    "function": {"name": "rag_query", "arguments": '{"query": "docs"}'},
                }
            ]
        },
    )
    assert _extract_tool_call(message) == {"name": "rag_query", "args": {"query": "docs"}}


def test_extract_tool_call_absent_returns_none() -> None:
    assert _extract_tool_call(AIMessage(content="just text")) is None


class FakeChatOllama:
    """Deterministic stand-in for ChatOllama: maps query prefixes to responses."""

    def __init__(self, base_url: str = "", model: str = "", temperature: float = 0.0, **_: Any):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature

    async def ainvoke(self, messages: list[Any], **_: Any) -> AIMessage:
        text = str(messages[-1].content)
        if text.startswith("raise:"):
            raise RuntimeError("simulated transport failure")
        if text.startswith("web:"):
            return AIMessage(content='{"tool": "web_search", "arguments": {"query": "find it"}}')
        if text.startswith("rag:"):
            return AIMessage(content='{"tool": "rag_query", "arguments": {"query": "docs"}}')
        if text.startswith("export:"):
            return AIMessage(
                content='{"tool": "file_export", "arguments": {"filename": "notes.txt"}}'
            )
        return AIMessage(content="No tool is needed for this question.")


@pytest.fixture
def stub_langchain_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = types.ModuleType("langchain_ollama")
    fake_module.ChatOllama = FakeChatOllama  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)


async def test_run_pilot_counts_successes_and_failure_reasons(
    stub_langchain_ollama: None,
) -> None:
    test_cases = [
        {"query": "web: flights to Lisbon", "expected_tool": "web_search"},
        {"query": "rag: retention policy", "expected_tool": "rag_query"},
        {"query": "export: save my notes", "expected_tool": "file_export"},
        {"query": "web: but expected rag", "expected_tool": "rag_query"},
        {"query": "just a plain question", "expected_tool": "web_search"},
        {"query": "raise: now", "expected_tool": "web_search"},
    ]

    result = await run_pilot("http://localhost:11434", "llama3.1:8b", test_cases=test_cases)

    assert result.total_tests == 6
    assert result.successes == 3
    assert result.failures == 3
    assert result.success_rate == pytest.approx(0.5)
    assert result.sample_size_warning is True
    assert result.failure_reasons["no_tool_call_detected"] == 1
    assert result.failure_reasons["wrong_tool: expected rag_query, got web_search"] == 1
    assert (
        sum(
            count
            for reason, count in result.failure_reasons.items()
            if reason.startswith("exception:")
        )
        == 1
    )
    assert result.verdict() == "rollback"
