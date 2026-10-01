"""Tests for AG-1 LangGraph agent graph."""

import json
from typing import Any

import pytest
from langchain_core.language_models import FakeListChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from llm_client.agent.cycle_detection import IterationMonitor
from llm_client.agent.graph import _tool_executor_node, build_agent_graph
from llm_client.transport.cancel import CancellationToken

# ── Helpers ───────────────────────────────────────────────────────────────────


class _MockTool:
    """Minimal BaseTool stand-in — records invocations, no network."""

    def __init__(self, name: str, result: Any = None, raises: Exception | None = None):
        self.name = name
        self._result = result
        self._raises = raises
        self.calls: list[dict] = []

    async def ainvoke(self, args: dict) -> Any:
        self.calls.append(args)
        if self._raises is not None:
            raise self._raises
        return self._result


def _ai_message_with_tool_calls(*tool_calls: dict) -> Any:
    """AIMessage carrying tool_calls, without going through a real LLM."""
    return AIMessage(content="", tool_calls=list(tool_calls))


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


# ── Phase 2 Tests (AG-5 web_search integration) ───────────────────────────────────


@pytest.mark.asyncio
async def test_build_agent_graph_phase2_default_tools():
    """Test build_agent_graph with default Phase 2 tools including web_search."""

    llm = FakeListChatModel(responses=["Hello world"])
    graph = build_agent_graph(llm)

    # Graph should have all default tools
    # This is mainly a smoke test - tool_executor will handle dispatch
    assert graph is not None


@pytest.mark.asyncio
async def test_build_agent_graph_phase2_custom_tools():
    """Test build_agent_graph with custom tools (web_search only)."""
    from llm_client.agent.tools import web_search

    llm = FakeListChatModel(responses=["Hello world"])
    graph = build_agent_graph(llm, tools=[web_search])

    # Graph should only have the specified tool
    assert graph is not None


# ── Phase 2 Tests (AG-6 rag_query + rag_retriever integration) ────────────────


class _MockRagPipeline:
    """Mock RagPipeline for testing rag_retriever node."""

    def __init__(self, chunks: list[dict] | None = None):
        self._chunks = chunks or [
            {"source_uri": "doc1", "title": "T1", "page": 1, "content_preview": "p1", "score": 0.9},
        ]
        self.retrieve_calls: list[dict] = []

    async def retrieve(self, query: str, top_k: int = 5) -> dict:
        self.retrieve_calls.append({"query": query, "top_k": top_k})
        return {
            "chunks": self._chunks[:top_k],
            "chunk_count": min(len(self._chunks), top_k),
            "top_score": self._chunks[0]["score"] if self._chunks else 0.0,
            "source_uris": [c["source_uri"] for c in self._chunks[:top_k] if c.get("source_uri")],
        }


def test_build_agent_graph_phase2_with_rag_pipeline():
    llm = FakeListChatModel(responses=["Hello"])
    pipeline = _MockRagPipeline()
    graph = build_agent_graph(llm, rag_pipeline=pipeline)
    assert graph is not None


def test_build_agent_graph_phase2_without_rag_pipeline():
    llm = FakeListChatModel(responses=["Hello"])
    graph = build_agent_graph(llm, rag_pipeline=None)
    assert graph is not None


def test_build_agent_graph_phase2_custom_rag_triggers():
    llm = FakeListChatModel(responses=["Hello"])
    pipeline = _MockRagPipeline()
    graph = build_agent_graph(llm, rag_pipeline=pipeline, rag_triggers=("custom",))
    assert graph is not None


@pytest.mark.asyncio
async def test_route_after_planner_rag_trigger_words():
    """User message with 'найди' should route to rag_retriever."""
    llm = FakeListChatModel(responses=["Here is what I found"])
    pipeline = _MockRagPipeline(chunks=[])
    graph = build_agent_graph(llm, rag_pipeline=pipeline)

    state = {
        "messages": [HumanMessage("найди документацию по asyncio")],
        "user_id": "u1",
        "session_id": "s1",
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": 0,
        "max_iterations": 10,
        "final_answer": None,
    }

    chunks = []
    async for chunk in graph.astream(state):
        chunks.append(chunk)

    # Should have gone through rag_retriever → final_answer
    node_names = set()
    for c in chunks:
        for k in c:
            if k not in ("messages", "iteration", "retrieved_docs", "final_answer"):
                node_names.add(k)
    assert "rag_retriever" in node_names or any("retrieved_docs" in c for c in chunks)


@pytest.mark.asyncio
async def test_route_after_planner_direct_llm_route():
    """User message without RAG triggers should go to final_answer."""
    llm = FakeListChatModel(responses=["Hello there!"])
    pipeline = _MockRagPipeline()
    graph = build_agent_graph(llm, rag_pipeline=pipeline)

    state = {
        "messages": [HumanMessage("привет")],
        "user_id": "u1",
        "session_id": "s1",
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": 0,
        "max_iterations": 10,
        "final_answer": None,
    }

    chunks = []
    async for chunk in graph.astream(state):
        chunks.append(chunk)

    # Should have gone directly to final_answer (no rag_retriever)
    node_names = set()
    for c in chunks:
        for k in c:
            if k not in ("messages", "iteration", "retrieved_docs", "final_answer"):
                node_names.add(k)
    assert "rag_retriever" not in node_names


@pytest.mark.asyncio
async def test_rag_retriever_node_extracts_query():
    """rag_retriever node should extract the last human message as query."""
    pipeline = _MockRagPipeline()
    from llm_client.agent.graph import _rag_retriever_node

    state = {
        "messages": [
            HumanMessage("previous message"),
            HumanMessage("найди информацию про Redis"),
        ],
    }

    result = await _rag_retriever_node(state, pipeline)

    assert "retrieved_docs" in result
    assert len(result["retrieved_docs"]) > 0
    assert pipeline.retrieve_calls[-1]["query"] == "найди информацию про Redis"


@pytest.mark.asyncio
async def test_rag_retriever_node_no_user_msg():
    """rag_retriever with no human messages returns empty docs."""
    pipeline = _MockRagPipeline()
    from llm_client.agent.graph import _rag_retriever_node

    state = {"messages": []}
    result = await _rag_retriever_node(state, pipeline)

    assert result["retrieved_docs"] == []


@pytest.mark.asyncio
async def test_rag_retriever_node_no_pipeline():
    """rag_retriever with None pipeline returns empty docs."""
    from llm_client.agent.graph import _rag_retriever_node

    state = {"messages": [HumanMessage("test")]}
    result = await _rag_retriever_node(state, None)

    assert result["retrieved_docs"] == []


@pytest.mark.asyncio
async def test_rag_retriever_node_with_pipeline():
    """rag_retriever with mock pipeline returns chunks."""
    chunks = [
        {"source_uri": "a", "title": "A", "page": 1, "content_preview": "x", "score": 0.95},
        {"source_uri": "b", "title": "B", "page": 2, "content_preview": "y", "score": 0.85},
    ]
    pipeline = _MockRagPipeline(chunks=chunks)
    from llm_client.agent.graph import _rag_retriever_node

    state = {"messages": [HumanMessage("search for something")], "rag_top_k": 2}
    result = await _rag_retriever_node(state, pipeline)

    assert len(result["retrieved_docs"]) == 2
    assert result["retrieved_docs"][0]["score"] == 0.95


@pytest.mark.asyncio
async def test_rag_retriever_node_uses_top_k_from_state():
    """rag_retriever uses rag_top_k from state if available."""
    pipeline = _MockRagPipeline(
        chunks=[
            {
                "source_uri": f"d{i}",
                "title": f"T{i}",
                "page": i,
                "content_preview": f"p{i}",
                "score": 0.9 - i * 0.1,
            }
            for i in range(10)
        ]
    )
    from llm_client.agent.graph import _rag_retriever_node

    state = {"messages": [HumanMessage("test")], "rag_top_k": 3}
    result = await _rag_retriever_node(state, pipeline)

    assert pipeline.retrieve_calls[-1]["top_k"] == 3
    assert len(result["retrieved_docs"]) == 3


@pytest.mark.asyncio
async def test_rag_trigger_search_english():
    """English trigger word 'search' should route to rag_retriever."""
    llm = FakeListChatModel(responses=["Found it"])
    pipeline = _MockRagPipeline(chunks=[])
    graph = build_agent_graph(llm, rag_pipeline=pipeline)

    state = {
        "messages": [HumanMessage("search for async patterns")],
        "user_id": "u1",
        "session_id": "s1",
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": 0,
        "max_iterations": 10,
        "final_answer": None,
    }

    chunks = []
    async for chunk in graph.astream(state):
        chunks.append(chunk)

    node_names = set()
    for c in chunks:
        for k in c:
            if k not in ("messages", "iteration", "retrieved_docs", "final_answer"):
                node_names.add(k)
    assert "rag_retriever" in node_names or any("retrieved_docs" in c for c in chunks)


@pytest.mark.asyncio
async def test_rag_trigger_find_english():
    """English trigger word 'find' should route to rag_retriever."""
    llm = FakeListChatModel(responses=["Here you go"])
    pipeline = _MockRagPipeline(chunks=[])
    graph = build_agent_graph(llm, rag_pipeline=pipeline)

    state = {
        "messages": [HumanMessage("find the documentation")],
        "user_id": "u1",
        "session_id": "s1",
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": 0,
        "max_iterations": 10,
        "final_answer": None,
    }

    chunks = []
    async for chunk in graph.astream(state):
        chunks.append(chunk)

    node_names = set()
    for c in chunks:
        for k in c:
            if k not in ("messages", "iteration", "retrieved_docs", "final_answer"):
                node_names.add(k)
    assert "rag_retriever" in node_names or any("retrieved_docs" in c for c in chunks)


@pytest.mark.asyncio
async def test_build_agent_graph_phase2_rag_first_stores_retrieved_docs():
    """After rag_retriever, state should contain retrieved_docs."""
    chunks = [
        {"source_uri": "doc1", "title": "T1", "page": 1, "content_preview": "p1", "score": 0.9},
    ]
    pipeline = _MockRagPipeline(chunks=chunks)
    llm = FakeListChatModel(responses=["Based on the documents..."])
    graph = build_agent_graph(llm, rag_pipeline=pipeline)

    state = {
        "messages": [HumanMessage("найди документ")],
        "user_id": "u1",
        "session_id": "s1",
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "iteration": 0,
        "max_iterations": 10,
        "final_answer": None,
    }

    final_chunks = []
    async for chunk in graph.astream(state):
        final_chunks.append(chunk)

    # Last chunk should have final_answer
    last = final_chunks[-1]
    assert "final_answer" in last


@pytest.mark.asyncio
async def test_tool_executor_dispatches_rag_query():
    """tool_executor should be able to dispatch rag_query tool calls."""
    from llm_client.agent.graph import _tool_executor_node
    from llm_client.agent.tools import rag_query

    state = {
        "messages": [
            type(
                "AIMessage",
                (),
                {
                    "tool_calls": [{"name": "rag_query", "args": {"query": "test"}, "id": "tc1"}],
                    "content": "",
                },
            )(),
        ],
    }

    result = await _tool_executor_node(state, [rag_query])
    messages = result["messages"]
    assert len(messages) == 1
    assert messages[0].tool_call_id == "tc1"


# ── H-3: multi-tool dispatch + settings wiring ────────────────────────────────


@pytest.mark.asyncio
async def test_route_after_planner_tool_calls():
    """An AIMessage carrying tool_calls must be routed to tool_executor."""
    tool = _MockTool("mock_tool", result={"ok": True})
    llm = FakeMessagesListChatModel(
        responses=[
            _ai_message_with_tool_calls(
                {"name": "mock_tool", "args": {"query": "q"}, "id": "tc1"}
            ),
            AIMessage(content="done"),
        ]
    )
    graph = build_agent_graph(llm, tools=[tool])

    chunks = []
    async for chunk in graph.astream(_initial_state("run the tool")):
        chunks.append(chunk)

    assert any("tool_executor" in c for c in chunks), "tool_executor node did not run"
    assert tool.calls == [{"query": "q"}]


@pytest.mark.asyncio
async def test_tool_executor_dispatches_web_search():
    """A web_search tool_call is dispatched and its list[dict] payload is JSON."""
    snippets = [
        {"title": "T1", "url": "http://a", "snippet": "s1", "score": 0.9},
        {"title": "T2", "url": "http://b", "snippet": "s2", "score": 0.7},
    ]
    tool = _MockTool("web_search", result=snippets)
    state = {
        "messages": [
            _ai_message_with_tool_calls(
                {"name": "web_search", "args": {"query": "test", "max_results": 5}, "id": "tc1"}
            )
        ]
    }

    result = await _tool_executor_node(state, [tool])
    messages = result["messages"]

    assert len(messages) == 1
    assert messages[0].tool_call_id == "tc1"
    assert messages[0].name == "web_search"
    assert tool.calls == [{"query": "test", "max_results": 5}]
    # H-4 parses this content with json.loads, so it must be valid JSON.
    assert json.loads(messages[0].content) == snippets


@pytest.mark.asyncio
async def test_tool_executor_unknown_tool():
    """An unknown tool_call yields an error ToolMessage instead of raising."""
    from llm_client.agent.tools import file_export

    state = {
        "messages": [
            _ai_message_with_tool_calls(
                {"name": "unknown_tool", "args": {}, "id": "tc1"}
            )
        ]
    }

    result = await _tool_executor_node(state, [file_export])
    messages = result["messages"]

    assert len(messages) == 1
    assert messages[0].tool_call_id == "tc1"
    payload = json.loads(messages[0].content)
    assert "Unknown tool: unknown_tool" in payload["error"]


@pytest.mark.asyncio
async def test_tool_executor_tool_error():
    """A raising tool is isolated: error ToolMessage, remaining calls still run."""
    failing = _MockTool("boom", raises=RuntimeError("upstream 503"))
    working = _MockTool("mock_tool", result={"ok": True})
    state = {
        "messages": [
            _ai_message_with_tool_calls(
                {"name": "boom", "args": {}, "id": "tc1"},
                {"name": "mock_tool", "args": {"x": 1}, "id": "tc2"},
            )
        ]
    }

    result = await _tool_executor_node(state, [failing, working])
    messages = result["messages"]

    assert len(messages) == 2
    error_payload = json.loads(messages[0].content)
    assert "upstream 503" in error_payload["error"]
    # The failure of one tool must not prevent the others from running.
    assert json.loads(messages[1].content) == {"ok": True}
    assert working.calls == [{"x": 1}]


def test_settings_filter_tools_enabled():
    """settings['tools_enabled'] selects a subset of the tool registry."""
    from llm_client.agent.service import DEFAULT_TOOLS_ENABLED, TOOL_REGISTRY, resolve_tools
    from llm_client.agent.tools import file_export, rag_query, web_search

    # Explicit subset — only file_export.
    tools = resolve_tools({"tools_enabled": ["file_export"]})
    assert tools == [file_export]

    # Omitting the key falls back to the full Phase 2 tool set.
    assert resolve_tools(None) == [file_export, web_search, rag_query]
    assert resolve_tools({}) == [file_export, web_search, rag_query]

    # An explicit empty list means "no tools", not "all tools".
    assert resolve_tools({"tools_enabled": []}) == []

    # Unknown names are ignored rather than raising.
    assert resolve_tools({"tools_enabled": ["nope", "rag_query"]}) == [rag_query]

    # A malformed value falls back to the defaults.
    assert resolve_tools({"tools_enabled": "file_export"}) == [file_export, web_search, rag_query]

    # Every default tool is present in the registry.
    for name in DEFAULT_TOOLS_ENABLED:
        assert name in TOOL_REGISTRY


# ── H-3: settings.top_k override for rag_retriever ───────────────────────────


@pytest.mark.asyncio
async def test_rag_retriever_uses_settings_top_k():
    """settings['top_k'] overrides the graph-level default (G-4)."""
    pipeline = _MockRagPipeline(
        chunks=[
            {"source_uri": f"d{i}", "title": f"T{i}", "page": i, "content_preview": "p", "score": 1.0}
            for i in range(8)
        ]
    )
    llm = FakeListChatModel(responses=["ok"])
    graph = build_agent_graph(llm, rag_pipeline=pipeline, settings={"top_k": 2})

    async for _ in graph.astream({**_initial_state("найди документацию"), "rag_top_k": 7}):
        pass

    assert pipeline.retrieve_calls[-1]["top_k"] == 2


@pytest.mark.asyncio
async def test_rag_retriever_invalid_settings_top_k_ignored():
    """A malformed settings['top_k'] falls back to the state value."""
    pipeline = _MockRagPipeline(
        chunks=[
            {"source_uri": f"d{i}", "title": f"T{i}", "page": i, "content_preview": "p", "score": 1.0}
            for i in range(8)
        ]
    )
    llm = FakeListChatModel(responses=["ok"])
    graph = build_agent_graph(llm, rag_pipeline=pipeline, settings={"top_k": "not-a-number"})

    async for _ in graph.astream({**_initial_state("найди документацию"), "rag_top_k": 3}):
        pass

    assert pipeline.retrieve_calls[-1]["top_k"] == 3


# ── H-4: rag_retriever is skipped when rag_query already answered ──────────────

_RAG_CHUNKS = [
    {"source_uri": "doc1", "title": "T1", "page": 1, "content_preview": "p1", "score": 0.9},
]


def _rag_query_llm(query: str, result: dict) -> FakeMessagesListChatModel:
    """LLM that calls rag_query once, then answers in plain text."""
    return FakeMessagesListChatModel(
        responses=[
            _ai_message_with_tool_calls(
                {"name": "rag_query", "args": {"query": query}, "id": "tc-rag"}
            ),
            AIMessage(content="Готово."),
        ]
    )


def _rag_query_tool(result: dict) -> Any:
    return _MockTool("rag_query", result=result)


async def _run(graph: Any, message: str) -> list[dict]:
    return [chunk async for chunk in graph.astream(_initial_state(message))]


def _node_names(chunks: list[dict]) -> set[str]:
    ignored = ("messages", "iteration", "retrieved_docs", "final_answer")
    return {key for chunk in chunks for key in chunk if key not in ignored}


@pytest.mark.asyncio
async def test_route_skips_rag_retriever_after_rag_query_tool_call():
    """Same question already answered by the tool — no duplicate retrieval."""
    pipeline = _MockRagPipeline(chunks=_RAG_CHUNKS)
    tool = _rag_query_tool(
        {
            "chunks": _RAG_CHUNKS,
            "chunk_count": 1,
            "top_score": 0.9,
            "source_uris": ["doc1"],
        }
    )
    graph = build_agent_graph(
        _rag_query_llm("найди документацию про asyncio", {}),
        tools=[tool],
        rag_pipeline=pipeline,
    )

    chunks = await _run(graph, "найди документацию про asyncio")

    assert "tool_executor" in _node_names(chunks)
    assert "rag_retriever" not in _node_names(chunks), "rag_retriever ran a duplicate query"
    assert pipeline.retrieve_calls == []
    assert tool.calls == [{"query": "найди документацию про asyncio"}]


@pytest.mark.asyncio
async def test_route_skips_rag_retriever_for_normalised_query_match():
    """Case and whitespace differences must not defeat the dedup."""
    pipeline = _MockRagPipeline(chunks=_RAG_CHUNKS)
    tool = _rag_query_tool({"chunks": _RAG_CHUNKS, "chunk_count": 1, "top_score": 0.9})
    graph = build_agent_graph(
        _rag_query_llm("  НАЙДИ   документацию про Asyncio  ", {}),
        tools=[tool],
        rag_pipeline=pipeline,
    )

    chunks = await _run(graph, "найди документацию про asyncio")

    assert "rag_retriever" not in _node_names(chunks)
    assert pipeline.retrieve_calls == []


@pytest.mark.asyncio
async def test_route_runs_rag_retriever_when_query_differs():
    """A decomposed query is new context — the heuristic route must still run."""
    pipeline = _MockRagPipeline(chunks=_RAG_CHUNKS)
    tool = _rag_query_tool({"chunks": _RAG_CHUNKS, "chunk_count": 1, "top_score": 0.9})
    graph = build_agent_graph(
        _rag_query_llm("пункт 5 договора", {}),
        tools=[tool],
        rag_pipeline=pipeline,
    )

    chunks = await _run(graph, "найди документацию про asyncio")

    assert "rag_retriever" in _node_names(chunks)
    assert pipeline.retrieve_calls[-1]["query"] == "найди документацию про asyncio"


@pytest.mark.asyncio
async def test_route_skips_rag_retriever_when_rag_query_returned_no_chunks():
    """An empty result is still an answer — the same query cannot yield more."""
    pipeline = _MockRagPipeline(chunks=_RAG_CHUNKS)
    tool = _rag_query_tool({"chunks": [], "chunk_count": 0, "top_score": 0.0})
    graph = build_agent_graph(
        _rag_query_llm("найди документацию про asyncio", {}),
        tools=[tool],
        rag_pipeline=pipeline,
    )

    chunks = await _run(graph, "найди документацию про asyncio")

    assert "rag_retriever" not in _node_names(chunks)
    assert pipeline.retrieve_calls == []


@pytest.mark.asyncio
async def test_route_runs_rag_retriever_when_rag_query_failed():
    """A tool error carries no chunks, so it must not count as an answer."""
    pipeline = _MockRagPipeline(chunks=_RAG_CHUNKS)
    tool = _rag_query_tool({"error": "Error: no corpus"})
    llm = FakeMessagesListChatModel(
        responses=[
            _ai_message_with_tool_calls(
                {
                    "name": "rag_query",
                    "args": {"query": "найди документацию про asyncio"},
                    "id": "tc1",
                }
            ),
            AIMessage(content="Попробую другой путь."),
        ]
    )
    graph = build_agent_graph(llm, tools=[tool], rag_pipeline=pipeline)

    chunks = await _run(graph, "найди документацию про asyncio")

    assert "rag_retriever" in _node_names(chunks)
    assert pipeline.retrieve_calls[-1]["query"] == "найди документацию про asyncio"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("найди документацию", "найди документацию"),
        ("  НАЙДИ   Документацию  ", "найди документацию"),
        ("найди\n\tдокументацию", "найди документацию"),
        ("", ""),
    ],
)
def test_normalise_query(raw: str, expected: str):
    """normalise_query folds case and whitespace, and is shared with the SSE layer."""
    from llm_client.agent.graph import normalise_query

    assert normalise_query(raw) == expected


def test_rag_query_answered_ignores_non_string_content():
    """A malformed ToolMessage (content blocks) must not raise."""
    from langchain_core.messages import ToolMessage

    from llm_client.agent.graph import _rag_query_answered

    messages = [
        _ai_message_with_tool_calls({"name": "rag_query", "args": {"query": "q"}, "id": "tc1"}),
        ToolMessage(content=[{"type": "text", "text": "x"}], tool_call_id="tc1", name="rag_query"),
    ]

    assert _rag_query_answered(messages, "q") is False
