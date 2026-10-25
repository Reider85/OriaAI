"""Pilot test: ADR-016 ReAct emulation on Ollama + Llama 3.1.

Bypasses LLMProviderFactory.create("ollama") (Phase 4 unblock);
uses ChatOllama directly from langchain-ollama (or
langchain-community fallback).

Pilot criteria (ROADMAP §14.1):
- ReAct success rate >=80% (vs native >=95%)
Rollback: success <60% OR false capability matrix entries.

Usage:
    python scripts/pilot_ollama_react.py --ollama-url http://localhost:11434 --model llama3.1:8b
    python scripts/pilot_ollama_react.py --variant v2_tolerant   # retune ReAct prompt (D-4)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 0.80
ROLLBACK_THRESHOLD = 0.60
MIN_SAMPLE_SIZE = 20
PROMPT_VARIANTS = ("v1_strict", "v2_tolerant", "v3_cot")


@dataclass
class PilotResult:
    """Aggregated pilot outcome for ADR-016 approval decision."""

    total_tests: int
    successes: int
    failures: int
    success_rate: float
    failure_reasons: dict[str, int]
    sample_size_warning: bool  # True if <20 tests

    def pilot_pass(self) -> bool:
        return self.success_rate >= PASS_THRESHOLD and not self.sample_size_warning

    def rollback_required(self) -> bool:
        return self.success_rate < ROLLBACK_THRESHOLD

    def verdict(self) -> str:
        if self.rollback_required():
            return "rollback"
        if self.pilot_pass():
            return "pass"
        return "partial"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tests": self.total_tests,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.success_rate, 4),
            "failure_reasons": dict(self.failure_reasons),
            "sample_size_warning": self.sample_size_warning,
            "verdict": self.verdict(),
        }


TEST_CASES: list[dict[str, str]] = [
    {"query": "Search the web for python asyncio best practices", "expected_tool": "web_search"},
    {"query": "Look up the latest stable release of Django", "expected_tool": "web_search"},
    {"query": "Find recent news about the EU AI Act", "expected_tool": "web_search"},
    {"query": "Search for the opening hours of the Louvre", "expected_tool": "web_search"},
    {
        "query": "What are the current best-selling science fiction novels?",
        "expected_tool": "web_search",
    },
    {"query": "Find the current price of Bitcoin", "expected_tool": "web_search"},
    {"query": "Search the web for flights from Berlin to Lisbon", "expected_tool": "web_search"},
    {
        "query": "Search the web for the Kubernetes 1.32 release notes",
        "expected_tool": "web_search",
    },
    {"query": "Find RAG documents about climate change", "expected_tool": "rag_query"},
    {
        "query": "What does our internal documentation say about the on-call rotation?",
        "expected_tool": "rag_query",
    },
    {"query": "Retrieve our meeting notes about the Q3 roadmap", "expected_tool": "rag_query"},
    {
        "query": "Search our knowledge base for the data retention policy",
        "expected_tool": "rag_query",
    },
    {"query": "Which of our indexed documents mention pgvector?", "expected_tool": "rag_query"},
    {
        "query": "Summarize what our docs say about checkpoint recovery",
        "expected_tool": "rag_query",
    },
    {"query": "Find internal pages about the billing refund process", "expected_tool": "rag_query"},
    {
        "query": "What information do we have stored about the Acme contract?",
        "expected_tool": "rag_query",
    },
    {"query": "Save my notes to a file", "expected_tool": "file_export"},
    {
        "query": "Export this conversation summary as a markdown file",
        "expected_tool": "file_export",
    },
    {"query": "Write the draft blog post into a text file", "expected_tool": "file_export"},
    {"query": "Create a file with my shopping list", "expected_tool": "file_export"},
    {"query": "Save the report as report.md", "expected_tool": "file_export"},
    {"query": "Dump these meeting minutes into a file for me", "expected_tool": "file_export"},
    {"query": "Export the analysis results to a file", "expected_tool": "file_export"},
    {"query": "Put this poem into a file called poem.txt", "expected_tool": "file_export"},
]


def _build_llm(ollama_url: str, model: str) -> Any:
    """Create ChatOllama without going through LLMProviderFactory (Phase 4 stub)."""
    try:
        from langchain_ollama import ChatOllama  # type: ignore[import-not-found]
    except ImportError:
        from langchain_community.chat_models import ChatOllama

    return ChatOllama(base_url=ollama_url, model=model, temperature=0.0)


def _extract_tool_call(response: Any) -> dict[str, Any] | None:
    """Normalize the first tool call of an AIMessage to {"name", "args"}.

    ReActBoundModel emits OpenAI-style entries in additional_kwargs; the
    AIMessage validator parses them into the normalized `tool_calls` field
    (name/args/id). Both shapes are accepted here.
    """
    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        first = tool_calls[0]
        if isinstance(first, dict) and first.get("name"):
            return {"name": first["name"], "args": first.get("args") or {}}

    additional = getattr(response, "additional_kwargs", None)
    if not isinstance(additional, dict):
        return None
    for raw in additional.get("tool_calls") or []:
        if not isinstance(raw, dict):
            continue
        function = raw.get("function")
        if not isinstance(function, dict):
            function = {}
        name = raw.get("tool") or raw.get("name") or function.get("name")
        if not name:
            continue
        args = raw.get("arguments") or raw.get("args") or function.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        return {"name": name, "args": args}
    return None


async def run_pilot(
    ollama_url: str,
    model: str,
    test_cases: list[dict[str, str]] | None = None,
    llm: Any = None,
) -> PilotResult:
    """Run pilot: send tool-calling prompts to Ollama + Llama 3.1 via
    ReActBoundModel; verify the extracted tool call matches the expectation."""
    from langchain_core.messages import HumanMessage

    from llm_client.agent.tool_calling_adapter import ToolCallingAdapter
    from llm_client.agent.tool_calling_mode import ToolCallingMode
    from llm_client.agent.tools.file_export import file_export
    from llm_client.agent.tools.rag_query import rag_query
    from llm_client.agent.tools.web_search import web_search

    chat = llm if llm is not None else _build_llm(ollama_url, model)
    adapter = ToolCallingAdapter()
    tools = [web_search, rag_query, file_export]

    bound = adapter.bind_tools(chat, tools, ToolCallingMode.REACT)

    cases = test_cases if test_cases is not None else TEST_CASES

    successes = 0
    failures = 0
    failure_reasons: dict[str, int] = {}
    for test in cases:
        expected_tool = test["expected_tool"]
        try:
            response = await bound.ainvoke([HumanMessage(content=test["query"])])
            tool_call = _extract_tool_call(response)
            if tool_call is None:
                failures += 1
                failure_reasons["no_tool_call_detected"] = (
                    failure_reasons.get("no_tool_call_detected", 0) + 1
                )
                continue
            if tool_call["name"] == expected_tool:
                successes += 1
            else:
                failures += 1
                reason = f"wrong_tool: expected {expected_tool}, got {tool_call['name']}"
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        except Exception as e:  # noqa: BLE001 — pilot must survive per-case errors
            failures += 1
            reason = f"exception: {type(e).__name__}: {str(e)[:100]}"
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    total = len(cases)
    success_rate = successes / total if total > 0 else 0.0
    return PilotResult(
        total_tests=total,
        successes=successes,
        failures=failures,
        success_rate=success_rate,
        failure_reasons=failure_reasons,
        sample_size_warning=total < MIN_SAMPLE_SIZE,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADR-016 ReAct pilot on Ollama + Llama 3.1")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument(
        "--variant",
        choices=PROMPT_VARIANTS,
        default=None,
        help="ReAct prompt variant (D-4), picked up via REACT_PROMPT_VARIANT",
    )
    parser.add_argument("--output", default=None, help="Optional path for a JSON pilot report")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.variant:
        os.environ["REACT_PROMPT_VARIANT"] = args.variant

    result = asyncio.run(run_pilot(args.ollama_url, args.model))

    print(f"=== ADR-016 Pilot: Ollama + {args.model} (ReAct) ===")
    print(f"Variant: {os.environ.get('REACT_PROMPT_VARIANT', 'v1_strict')}")
    print(f"Total tests: {result.total_tests}")
    print(f"Successes: {result.successes}")
    print(f"Failures: {result.failures}")
    print(f"Success rate: {result.success_rate:.1%}")
    print(f"Failure reasons: {result.failure_reasons}")
    if result.sample_size_warning:
        print(f"Sample size warning: {result.total_tests} tests (<{MIN_SAMPLE_SIZE})")
    print()

    if result.verdict() == "rollback":
        print(f"ROLLBACK REQUIRED (success rate <{ROLLBACK_THRESHOLD:.0%})")
    elif result.verdict() == "pass":
        print(f"PILOT PASS - ADR-016 Approved (success rate >={PASS_THRESHOLD:.0%})")
    else:
        print(
            f"PILOT PARTIAL - success rate {result.success_rate:.1%} "
            f"(need >={PASS_THRESHOLD:.0%}; tune ReAct prompt via --variant and re-run)"
        )

    if args.output:
        report = {
            "pilot": "adr-016-react-ollama",
            "ollama_url": args.ollama_url,
            "model": args.model,
            "react_prompt_variant": os.environ.get("REACT_PROMPT_VARIANT", "v1_strict"),
            **result.to_dict(),
        }
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
