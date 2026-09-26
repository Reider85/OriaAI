"""LangGraph agent graph for agent-service (AG-1 / AG-4).

Minimal Phase 1 graph: planner + tool_executor + final_answer nodes.
Integrates IterationMonitor (cycle detection) and CancellationToken.
AG-4 adds tool_executor node and bind_tools wiring.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from ..transport.cancel import CancellationToken
from .cycle_detection import IterationMonitor

logger = logging.getLogger(__name__)


# ── Agent state schema ────────────────────────────────────────────────────────


class AgentState(TypedDict, total=False):
    """State schema for the LangGraph agent.

    ``messages`` uses ``add_messages`` so successive nodes append rather than
    replace — required for the planner ↔ tool_executor loop.
    """

    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    provider: str
    model_name: str
    iteration: int
    max_iterations: int
    final_answer: str | None


# ── Node functions ────────────────────────────────────────────────────────────


async def _planner_node(
    state: dict[str, Any], llm: BaseChatModel
) -> dict[str, Any]:
    """Invoke the LLM and return the assistant message + incremented iteration."""
    response = await llm.ainvoke(state["messages"])
    return {
        "messages": [response],
        "iteration": state.get("iteration", 0) + 1,
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


async def _tool_executor_node(
    state: dict[str, Any], tools: list[Any]
) -> dict[str, Any]:
    """Execute every tool_call in the last AIMessage and return ToolMessages."""
    messages = state.get("messages") or []
    if not messages:
        return {"messages": []}

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None)
    if not tool_calls:
        return {"messages": []}

    tools_by_name = {getattr(t, "name", None): t for t in tools}
    results: list[ToolMessage] = []
    for tc in tool_calls:
        name = tc["name"]
        args = tc["args"]
        matched = tools_by_name.get(name)
        if matched is not None:
            result = await matched.ainvoke(args)
            result_str = json.dumps(result) if isinstance(result, dict) else str(result)
        else:
            result_str = json.dumps({"error": f"Unknown tool: {name}"})
        results.append(
            ToolMessage(content=result_str, tool_call_id=tc["id"], name=name)
        )
    return {"messages": results}


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
        tools:  Optional tool list (e.g. ``[file_export]``).  When provided the
                planner is bound via ``llm.bind_tools()`` and a ``tool_executor``
                node is wired into the graph.
        monitor: Optional IterationMonitor — called after each planner iteration.

    Returns:
        Compiled LangGraph graph ready for ``graph.astream(state)``.
    """
    # ── Bind tools to LLM (AG-4) ─────────────────────────────────────────────
    bound_llm = llm
    if tools:
        try:
            bound_llm = llm.bind_tools(tools)
        except (NotImplementedError, AttributeError) as exc:
            logger.warning(
                "LLM does not support bind_tools (%s); tool calls disabled", exc
            )

    graph = StateGraph(AgentState)

    # ── Nodes ────────────────────────────────────────────────────────────────

    async def planner(state: dict[str, Any]) -> dict[str, Any]:
        return await _planner_node(state, bound_llm)

    def final_answer(state: dict[str, Any]) -> dict[str, Any]:
        return _final_answer_node(state)

    async def tool_executor(state: dict[str, Any]) -> dict[str, Any]:
        return await _tool_executor_node(state, tools or [])

    graph.add_node("planner", planner)
    graph.add_node("final_answer", final_answer)
    if tools:
        graph.add_node("tool_executor", tool_executor)

    # ── Edges ────────────────────────────────────────────────────────────────

    def route_after_planner(state: dict[str, Any]) -> str:
        # Cancel check BETWEEN nodes only (C-4 requirement)
        if token is not None and token.is_cancelled:
            logger.info("Graph exiting — token cancelled before final_answer")
            return END

        # Cycle detection via monitor
        if monitor is not None and monitor.check(state):
            logger.warning("Graph exiting — cycle detected by IterationMonitor")
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

        # Tool calls → tool_executor (AG-4)
        if tools:
            messages = state.get("messages") or []
            if messages:
                last = messages[-1]
                if getattr(last, "tool_calls", None):
                    return "tool_executor"

        return "final_answer"

    graph.set_entry_point("planner")

    planner_routes: dict[str, Any] = {"final_answer": "final_answer", END: END}
    if tools:
        planner_routes["tool_executor"] = "tool_executor"
    graph.add_conditional_edges("planner", route_after_planner, planner_routes)

    if tools:
        graph.add_edge("tool_executor", "planner")

    graph.add_edge("final_answer", END)

    return graph.compile()
