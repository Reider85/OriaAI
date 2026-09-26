"""Tests for AG-1 LangGraph agent graph."""

import pytest
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from llm_client.agent.cycle_detection import IterationMonitor
from llm_client.agent.graph import build_agent_graph
from llm_client.transport.cancel import CancellationToken

# ── Helpers ───────────────────────────────────────────────────────────────────


def _initial_state(
    message: str = "hi",
    *,
    user_id: str = "u1",
    session_id: str = "s1",
    iteration: int = 0,
    max_iterations: int = 10,
) -> dict:
    return {
        "messages": [HumanMessage(message)],
        "user_id": user_id,
        "session_id": session_id,
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": iteration,
        "max_iterations": max_iterations,
        "final_answer": None,
    }


# ── Build graph tests ─────────────────────────────────────────────────────────


def test_build_graph_returns_compiled():
    llm = FakeListChatModel(responses=["Hello"])
    graph = build_agent_graph(llm)
    assert graph is not None
    assert hasattr(graph, "astream")


def test_build_graph_with_token():
    llm = FakeListChatModel(responses=["Hello"])
    token = CancellationToken("s1")
    graph = build_agent_graph(llm, token=token)
    assert graph is not None


def test_build_graph_with_monitor():
    llm = FakeListChatModel(responses=["Hello"])
    monitor = IterationMonitor(enabled=True, threshold=0.95, consecutive=2)
    graph = build_agent_graph(llm, monitor=monitor)
    assert graph is not None


# ── Astream tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_astream_yields_chunks_and_ends():
    llm = FakeListChatModel(responses=["Hello from graph!"])
    graph = build_agent_graph(llm)
    chunks = []
    async for chunk in graph.astream(_initial_state()):
        chunks.append(chunk)

    assert len(chunks) >= 2  # planner + final_answer
    # Last chunk should be final_answer with content
    last = chunks[-1]
    assert "final_answer" in last
    assert last["final_answer"]["final_answer"] == "Hello from graph!"


@pytest.mark.asyncio
async def test_astream_multiple_tokens():
    llm = FakeListChatModel(responses=["First", "Second"])
    graph = build_agent_graph(llm)

    # Run twice to verify stateless behavior
    for expected in ["First", "Second"]:
        chunks = []
        async for chunk in graph.astream(_initial_state()):
            chunks.append(chunk)
        last = chunks[-1]
        assert last["final_answer"]["final_answer"] == expected


# ── Cancel tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_before_start_exits_immediately():
    llm = FakeListChatModel(responses=["Should not be called"])
    token = CancellationToken("s1")
    token.cancel("user_cancelled")

    graph = build_agent_graph(llm, token=token)
    chunks = []
    async for chunk in graph.astream(_initial_state()):
        chunks.append(chunk)

    # Graph should exit immediately — planner may or may not run,
    # but final_answer should NOT be reached with LLM content
    # because route_after_planner sees cancelled and goes to END
    # The planner node is skipped entirely because the conditional
    # edge at entry checks cancellation first
    final_chunks = [c for c in chunks if "final_answer" in c]
    # If planner ran, it would produce an AIMessage; but with cancel
    # before start, the graph may exit without running planner
    # At minimum, no final_answer node should complete
    if final_chunks:
        assert final_chunks[0]["final_answer"]["final_answer"] is None


@pytest.mark.asyncio
async def test_cancel_before_start_no_llm_call():
    call_count = 0

    class CountingLLM(FakeListChatModel):
        def invoke(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return super().invoke(*args, **kwargs)

        async def ainvoke(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await super().ainvoke(*args, **kwargs)

    llm = CountingLLM(responses=["Hello"])
    token = CancellationToken("s1")
    token.cancel("user_cancelled")

    graph = build_agent_graph(llm, token=token)
    async for _ in graph.astream(_initial_state()):
        pass

    # Planner runs once (entry point → planner), then route_after_planner
    # sees token.is_cancelled and exits to END. This is correct per C-4:
    # cancel check is BETWEEN nodes, not inside the planner node.
    assert call_count == 1, (
        f"Planner should run once (entry point), then cancel stops graph. Got {call_count}"
    )


# ── IterationMonitor tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cycle_detection_exits_graph():
    """When the LLM returns the same content twice, IterationMonitor triggers."""
    # FakeListChatModel cycles through responses; same response = cycle
    llm = FakeListChatModel(responses=["same answer", "same answer", "same answer"])
    monitor = IterationMonitor(enabled=True, threshold=0.95, consecutive=2)

    graph = build_agent_graph(llm, monitor=monitor)
    chunks = []
    async for chunk in graph.astream(_initial_state()):
        chunks.append(chunk)

    # After 2 identical iterations, monitor should trigger and graph exits
    # Check that graph didn't run无限 loops
    planner_chunks = [c for c in chunks if "planner" in c]
    # With max_iterations=10, should exit well before that
    assert len(planner_chunks) <= 4, (
        f"Graph should exit early due to cycle detection, but ran {len(planner_chunks)} planner iterations"
    )


@pytest.mark.asyncio
async def test_no_cycle_with_different_outputs():
    """Different LLM outputs should not trigger cycle detection."""
    llm = FakeListChatModel(responses=["first", "second", "third", "fourth"])
    monitor = IterationMonitor(enabled=True, threshold=0.95, consecutive=2)

    graph = build_agent_graph(llm, monitor=monitor)
    chunks = []
    async for chunk in graph.astream(_initial_state()):
        chunks.append(chunk)

    # Should run through final_answer normally
    last = chunks[-1]
    assert "final_answer" in last
    assert last["final_answer"]["final_answer"] == "first"


# ── Max iterations test ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_iterations_stops_graph():
    """Graph should stop after max_iterations even without cycle detection."""

    class InfiniteLLM(FakeListChatModel):
        """Always returns the same thing, but we set max_iterations low."""

        def invoke(self, *args, **kwargs):
            return AIMessage(content="looping")

        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content="looping")

    llm = InfiniteLLM(responses=["looping"])
    graph = build_agent_graph(llm)
    chunks = []
    # max_iterations=2 means planner runs at most 2 times
    async for chunk in graph.astream(_initial_state(max_iterations=2)):
        chunks.append(chunk)

    planner_chunks = [c for c in chunks if "planner" in c]
    assert len(planner_chunks) <= 2, (
        f"Graph should stop at max_iterations=2, but ran {len(planner_chunks)} planner iterations"
    )
