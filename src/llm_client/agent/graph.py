"""LangGraph agent graph for agent-service (AG-1 / AG-4, Phase 2 AG-6).

Phase 1 graph: planner + tool_executor + final_answer nodes.
Phase 2 extensions: rag_retriever node, route_after_planner with 3
outputs (direct_llm / tools_needed / rag_first).
Integrates IterationMonitor (cycle detection) and CancellationToken.
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

# Default trigger words for rag_first routing (Phase 2 simplified heuristic).
_RAG_TRIGGERS = ("найди", "search", "find", "документ", "look up", "поиск")


# ── Agent state schema ────────────────────────────────────────────────────────


class AgentState(TypedDict, total=False):
    """State schema for the LangGraph agent.

    ``messages`` uses ``add_messages`` so successive nodes append rather than
    replace — required for the planner ↔ tool_executor loop.
    ``retrieved_docs`` is populated by the rag_retriever node (Phase 2 AG-6).
    ``rag_top_k`` is the per-run retrieval depth override; it must stay declared
    here or LangGraph drops it from the input state and the rag_retriever
    fallback silently degrades to its own default.
    """

    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    provider: str
    model_name: str
    iteration: int
    max_iterations: int
    final_answer: str | None
    retrieved_docs: list[dict[str, Any]]
    rag_top_k: int


# ── Node functions ────────────────────────────────────────────────────────────


async def _planner_node(state: dict[str, Any], llm: BaseChatModel) -> dict[str, Any]:
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


async def _tool_executor_node(state: dict[str, Any], tools: list[Any]) -> dict[str, Any]:
    """Execute every tool_call in the last AIMessage and return ToolMessages.

    Each dispatch is isolated: an unknown tool or a raising tool yields an error
    ToolMessage for that call only, so one failure cannot abort the rest of the
    batch or crash the graph. Result payloads are JSON-encoded when they are
    dicts or lists, which keeps them parseable by the SSE layer (H-4).
    """
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
            try:
                result = await matched.ainvoke(args)
            except Exception as exc:
                logger.exception("Tool %s failed", name)
                result_str = json.dumps({"error": f"Error: {exc}"})
            else:
                result_str = (
                    json.dumps(result) if isinstance(result, (dict, list)) else str(result)
                )
        else:
            result_str = json.dumps({"error": f"Unknown tool: {name}"})
        results.append(ToolMessage(content=result_str, tool_call_id=tc["id"], name=name))
    return {"messages": results}


async def _rag_retriever_node(
    state: dict[str, Any],
    pipeline: Any,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Retrieve documents from RAG corpus based on last user message.

    Called when planner decides 'rag_first' strategy. Updates
    state['retrieved_docs'] for final_answer node to use as context.

    ``top_k`` is the graph-level override coming from the UI settings panel
    (G-4, see ``build_agent_graph(settings=...)``). It takes precedence over the
    per-run ``state['rag_top_k']`` value.
    """
    if pipeline is None:
        return {"retrieved_docs": []}

    messages = state.get("messages") or []
    last_user_msg = None
    for m in reversed(messages):
        if getattr(m, "type", "") == "human" or getattr(m, "role", "") == "user":
            last_user_msg = m
            break
    if last_user_msg is None:
        return {"retrieved_docs": []}

    query = last_user_msg.content if hasattr(last_user_msg, "content") else str(last_user_msg)
    effective_top_k = top_k if top_k is not None else state.get("rag_top_k", 5)

    result = await pipeline.retrieve(query, top_k=effective_top_k)
    return {"retrieved_docs": result["chunks"]}


# ── Graph builder ─────────────────────────────────────────────────────────────


def _resolve_top_k_override(settings: dict[str, Any] | None) -> int | None:
    """Extract the ``top_k`` retrieval override from the UI settings payload.

    Returns None when absent or invalid, so the rag_retriever node falls back to
    ``state['rag_top_k']`` (and then to its own default). Settings come straight
    off the wire (G-4), hence the defensive coercion.
    """
    if not settings or "top_k" not in settings:
        return None

    raw = settings["top_k"]
    try:
        top_k = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid settings['top_k']=%r — ignoring override", raw)
        return None

    if top_k <= 0:
        logger.warning("Non-positive settings['top_k']=%r — ignoring override", raw)
        return None
    return top_k


def build_agent_graph(
    llm: BaseChatModel,
    token: CancellationToken | None = None,
    tools: list[Any] | None = None,
    *,
    monitor: IterationMonitor | None = None,
    checkpointer: Any | None = None,
    rag_pipeline: Any | None = None,
    rag_triggers: tuple[str, ...] | None = None,
    settings: dict[str, Any] | None = None,
) -> Any:
    """Construct and compile the agent graph (Phase 1 + Phase 2).

    Phase 2 extensions over Phase 1 (AG-1):
    - rag_pipeline: singleton RagPipeline (H-2). None disables rag_retriever.
    - rag_retriever node added when rag_pipeline is not None.
    - route_after_planner extended: 3 exits (direct_llm / tools_needed /
      rag_first). Simplified heuristic routes rag_first when user message
      contains trigger words.

    Args:
        llm:    LangChain chat model.
        token:  Optional CancellationToken — checked between nodes (C-4).
        tools:  Optional tool list (e.g. ``[file_export, web_search, rag_query]``).
                Filtered upstream by the ``settings['tools_enabled']`` list.
        monitor: Optional IterationMonitor — cycle detection.
        checkpointer: Optional LangGraph checkpointer.
        rag_pipeline: Optional RagPipeline — enables rag_retriever node.
        rag_triggers: Optional tuple of trigger words for rag_first routing.
        settings: Optional UI settings panel payload (G-4). Only ``top_k`` is
            consumed here, and it is applied via the node closure rather than
            threaded through graph state.

    Returns:
        Compiled LangGraph graph ready for ``graph.astream(state)``.
    """
    # ── Bind tools to LLM (AG-4) ─────────────────────────────────────────────
    bound_llm = llm
    if tools:
        try:
            bound_llm = llm.bind_tools(tools)
        except (NotImplementedError, AttributeError) as exc:
            logger.warning("LLM does not support bind_tools (%s); tool calls disabled", exc)

    triggers = rag_triggers or _RAG_TRIGGERS
    top_k_override = _resolve_top_k_override(settings)

    graph = StateGraph(AgentState)

    # ── Nodes ────────────────────────────────────────────────────────────────

    async def planner(state: dict[str, Any]) -> dict[str, Any]:
        return await _planner_node(state, bound_llm)

    def final_answer(state: dict[str, Any]) -> dict[str, Any]:
        return _final_answer_node(state)

    async def tool_executor(state: dict[str, Any]) -> dict[str, Any]:
        return await _tool_executor_node(state, tools or [])

    async def rag_retriever(state: dict[str, Any]) -> dict[str, Any]:
        return await _rag_retriever_node(state, rag_pipeline, top_k=top_k_override)

    graph.add_node("planner", planner)
    graph.add_node("final_answer", final_answer)
    if tools:
        graph.add_node("tool_executor", tool_executor)
    if rag_pipeline is not None:
        graph.add_node("rag_retriever", rag_retriever)

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

        # Phase 2: rag_first heuristic route
        if rag_pipeline is not None:
            user_msg = None
            for m in reversed(state.get("messages") or []):
                if getattr(m, "type", "") == "human":
                    user_msg = m
                    break
            if user_msg is not None:
                content_lower = (getattr(user_msg, "content", "") or "").lower()
                if any(t in content_lower for t in triggers):
                    return "rag_retriever"

        return "final_answer"

    graph.set_entry_point("planner")

    planner_routes: dict[str, Any] = {"final_answer": "final_answer", END: END}
    if tools:
        planner_routes["tool_executor"] = "tool_executor"
    if rag_pipeline is not None:
        planner_routes["rag_retriever"] = "rag_retriever"
    graph.add_conditional_edges("planner", route_after_planner, planner_routes)

    if tools:
        graph.add_edge("tool_executor", "planner")

    # rag_retriever → final_answer (after retrieval — form response)
    if rag_pipeline is not None:
        graph.add_edge("rag_retriever", "final_answer")

    graph.add_edge("final_answer", END)

    return graph.compile(checkpointer=checkpointer)
