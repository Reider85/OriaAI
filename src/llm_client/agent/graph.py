"""LangGraph agent graph for agent-service (AG-1).

Minimal Phase 1 graph: planner + final_answer nodes, one conditional edge.
Integrates IterationMonitor (cycle detection) and CancellationToken.
No tools in Phase 1 — AG-4 will add file_export.
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, StateGraph

from ..transport.cancel import CancellationToken
from .cycle_detection import IterationMonitor

logger = logging.getLogger(__name__)


# ── Agent state schema ────────────────────────────────────────────────────────


class AgentState(dict):  # type: ignore[type-arg]
    """TypedDict-compatible state for the LangGraph agent.

    Fields:
        messages:      Conversation history (LangGraph add_messages reducer).
        user_id:       Caller identifier (for observability, masked in logs).
        session_id:    Unique session key.
        provider:      LLM provider name ("openai" in Phase 1).
        model_name:    Model identifier (e.g. "gpt-4o-mini").
        iteration:     Current loop counter (starts at 0).
        max_iterations: Circuit-breaker limit (default 10, ADR-001).
        final_answer:  Extracted assistant text (None until terminal node).
        streaming_tokens: Accumulated token strings for partial answer on cancel.
    """

    # We subclass dict for simplicity; TypedDict is runtime-incompatible with
    # StateGraph which expects a plain dict-like state.


# ── Node functions ────────────────────────────────────────────────────────────


async def _planner_node(state: dict[str, Any], llm: BaseChatModel) -> dict[str, Any]:
    """Invoke the LLM and return the assistant message + incremented iteration."""
    response = await llm.ainvoke(state["messages"])
    return {
        "messages": [response],
        "iteration": state["iteration"] + 1,
    }


def _final_answer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Extract the last assistant message into final_answer."""
    messages = state.get("messages") or []
    if messages:
        last = messages[-1]
        content = last.content if hasattr(last, "content") else str(last)
    else:
        content = ""
    return {"final_answer": content, "messages": []}


# ── Graph builder ─────────────────────────────────────────────────────────────


def build_agent_graph(
    llm: BaseChatModel,
    token: CancellationToken | None = None,
    tools: list[Any] | None = None,
    *,
    monitor: IterationMonitor | None = None,
) -> Any:
    """Construct and compile the Phase 1 agent graph.

    Args:
        llm:    LangChain chat model (from LLMProviderFactory or FakeListChatModel).
        token:  Optional CancellationToken — checked between nodes (C-4).
        tools:  Reserved for AG-4+ (file_export). Ignored in Phase 1.
        monitor: Optional IterationMonitor — called after each planner iteration.

    Returns:
        Compiled LangGraph graph ready for ``graph.astream(state)``.
    """
    graph = StateGraph(dict)

    # ── Nodes ────────────────────────────────────────────────────────────────

    async def planner(state: dict[str, Any]) -> dict[str, Any]:
        return await _planner_node(state, llm)

    def final_answer(state: dict[str, Any]) -> dict[str, Any]:
        return _final_answer_node(state)

    graph.add_node("planner", planner)
    graph.add_node("final_answer", final_answer)

    # ── Edges ────────────────────────────────────────────────────────────────

    def route_after_planner(state: dict[str, Any]) -> str:
        # Cancel check BETWEEN nodes only (C-4 requirement)
        if token is not None and token.is_cancelled:
            logger.info("Graph exiting — token cancelled before final_answer")
            return END

        # Cycle detection via monitor
        if monitor is not None and monitor.check(state):
            logger.warning("Graph exiting — cycle detected by IterationMonitor")
            # Write partial answer from last message before exiting
            messages = state.get("messages") or []
            if messages:
                last = messages[-1]
                content = last.content if hasattr(last, "content") else str(last)
                state["final_answer"] = content
            return END

        # Iteration limit
        if state.get("iteration", 0) >= state.get("max_iterations", 10):
            logger.warning(
                "Graph exiting — max_iterations (%s) reached",
                state.get("max_iterations", 10),
            )
            return END

        return "final_answer"

    graph.set_entry_point("planner")
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "final_answer": "final_answer",
            END: END,
        },
    )
    graph.add_edge("final_answer", END)

    return graph.compile()
