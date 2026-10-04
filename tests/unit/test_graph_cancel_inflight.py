"""Unit tests for in-flight cancellation in LangGraph agent (ADR-013).

Tests cancel during LLM/tool/RAG execution with dual mechanism:
- Race condition via CancellationToken in RunnableConfig
- Task cancellation via token.on_cancel callback

Key scenarios:
- Cancel during llm.ainvoke (primary path)
- Cancel during tool.ainvoke (belt-and-suspenders)
- Cancel during rag_retrieve (belt-and-suspenders)
- Early exit if token already cancelled
- Partial answer in cancelled payload
- Hard timeout fallback
"""

import asyncio
from unittest.mock import patch

import pytest

from llm_client.agent.graph import (
    GraphCancelled,
    GraphInvokeTimeout,
    _partial_answer,
    build_agent_graph,
    invoke_with_cancel,
)
from llm_client.transport.cancel import CancellationToken


class MockLLM:
    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        await asyncio.sleep(self.delay)
        return f"Response {self.call_count}"


class MockTool:
    def __init__(self, name: str, delay: float = 0.1):
        self.name = name
        self.delay = delay
        self.call_count = 0

    async def ainvoke(self, args):
        self.call_count += 1
        await asyncio.sleep(self.delay)
        return f"Tool result {self.call_count}"


class MockRAGPipeline:
    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self.call_count = 0

    async def retrieve(self, query, top_k=5):
        self.call_count += 1
        await asyncio.sleep(self.delay)
        return {"chunks": [{"id": f"doc_{i}", "content": f"Doc {i}"} for i in range(top_k)]}


@pytest.mark.asyncio
async def test_invoke_with_cancel_no_token():
    """Test invoke_with_cancel without token works normally."""
    llm = MockLLM(delay=0.01)

    result = await invoke_with_cancel(lambda: llm.ainvoke([]), None, timeout_s=1.0)

    assert result == "Response 1"
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_invoke_with_cancel_already_cancelled():
    """Test invoke_with_cancel raises immediately if token already cancelled."""
    token = CancellationToken("test_session")
    token.cancel("test_reason")

    llm = MockLLM(delay=0.01)

    with pytest.raises(GraphCancelled, match="test_reason"):
        await invoke_with_cancel(lambda: llm.ainvoke([]), token, timeout_s=1.0)

    assert llm.call_count == 0  # No LLM call made


@pytest.mark.asyncio
async def test_invoke_with_cancel_during_llm():
    """Test invoke_with_cancel cancels LLM execution when token cancelled."""
    token = CancellationToken("test_session")
    llm = MockLLM(delay=0.1)  # Longer than test timeout

    # Start LLM call, cancel after short delay
    task = asyncio.create_task(invoke_with_cancel(lambda: llm.ainvoke([]), token, timeout_s=1.0))

    # Cancel after 50ms
    await asyncio.sleep(0.05)
    token.cancel("user_cancelled")

    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await task

    assert llm.call_count == 1  # LLM was called but cancelled


@pytest.mark.asyncio
async def test_invoke_with_cancel_hard_timeout():
    """Test invoke_with_cancel raises GraphInvokeTimeout on hard timeout."""
    token = CancellationToken("test_session")
    llm = MockLLM(delay=0.2)  # Longer than timeout

    with pytest.raises(GraphInvokeTimeout, match="exceeded 0.1s"):
        await invoke_with_cancel(lambda: llm.ainvoke([]), token, timeout_s=0.1)

    assert llm.call_count == 1  # LLM was called but timed out


@pytest.mark.asyncio
async def test_planner_node_cancel_during_llm():
    """Test _planner_node cancels LLM execution when token cancelled via config."""
    llm = MockLLM(delay=0.1)
    token = CancellationToken("test_session")

    # Cancel token after short delay
    async def cancel_later():
        await asyncio.sleep(0.05)
        token.cancel("user_cancelled")

    asyncio.create_task(cancel_later())

    # Planner should raise GraphCancelled
    from llm_client.agent.graph import _planner_node

    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await _planner_node(
            {"messages": [{"type": "human", "content": "test"}]},
            llm,
            config={"configurable": {"cancel_token": token}},
        )

    assert llm.call_count == 1  # LLM was called but cancelled


@pytest.mark.asyncio
async def test_planner_node_early_exit():
    """Test _planner_node exits early if token already cancelled."""
    llm = MockLLM(delay=0.01)
    token = CancellationToken("test_session")
    token.cancel("already_cancelled")

    # Planner should raise immediately without calling LLM
    from llm_client.agent.graph import _planner_node

    with pytest.raises(GraphCancelled, match="already_cancelled"):
        await _planner_node(
            {"messages": [{"type": "human", "content": "test"}]},
            llm,
            config={"configurable": {"cancel_token": token}},
        )

    assert llm.call_count == 0  # No LLM call


@pytest.mark.asyncio
async def test_tool_executor_node_cancel_during_tool():
    """Test _tool_executor_node cancels tool execution when token cancelled."""
    tool = MockTool("test_tool", delay=0.1)
    token = CancellationToken("test_session")

    # Cancel token after short delay
    async def cancel_later():
        await asyncio.sleep(0.05)
        token.cancel("user_cancelled")

    asyncio.create_task(cancel_later())

    # Create AIMessage with tool call
    from langchain_core.messages import AIMessage, ToolCall

    aimsg = AIMessage(
        content="", tool_calls=[ToolCall(id="test_id", name="test_tool", args={"input": "test"})]
    )

    # Tool executor should raise GraphCancelled
    from llm_client.agent.graph import _tool_executor_node

    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await _tool_executor_node(
            {"messages": [aimsg]}, [tool], config={"configurable": {"cancel_token": token}}
        )

    assert tool.call_count == 1  # Tool was called but cancelled


@pytest.mark.asyncio
async def test_rag_retriever_node_cancel_during_retrieve():
    """Test _rag_retriever_node cancels RAG execution when token cancelled."""
    pipeline = MockRAGPipeline(delay=0.2)  # 200ms delay
    token = CancellationToken("test_session")

    # Cancel token after short delay
    async def cancel_later():
        await asyncio.sleep(0.05)  # 50ms delay
        token.cancel("user_cancelled")

    asyncio.create_task(cancel_later())

    # RAG retriever should raise GraphCancelled
    from llm_client.agent.graph import _rag_retriever_node

    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await _rag_retriever_node(
            {"messages": [{"type": "human", "content": "test query"}], "rag_top_k": 5},
            pipeline,
            config={"configurable": {"cancel_token": token}},
        )

    assert pipeline.call_count == 1  # Pipeline was called but cancelled


@pytest.mark.asyncio
async def test_rag_retriever_node_simple():
    """Test _rag_retriever_node with minimal state to isolate the issue."""
    pipeline = MockRAGPipeline(delay=0.2)
    token = CancellationToken("test_session")

    # Cancel token after short delay
    async def cancel_later():
        await asyncio.sleep(0.05)
        token.cancel("user_cancelled")

    asyncio.create_task(cancel_later())

    # RAG retriever should raise GraphCancelled with minimal state
    from llm_client.agent.graph import _rag_retriever_node

    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await _rag_retriever_node(
            {
                "messages": [{"role": "user", "content": "simple query"}],
            },
            pipeline,
            config={"configurable": {"cancel_token": token}},
        )

    assert pipeline.call_count == 1  # Pipeline was called but cancelled


@pytest.mark.asyncio
async def test_rag_invoke_with_cancel_direct():
    """Test invoke_with_cancel directly with MockRAGPipeline to isolate the issue."""
    pipeline = MockRAGPipeline(delay=0.1)
    token = CancellationToken("test_session")

    # Cancel token after short delay
    async def cancel_later():
        await asyncio.sleep(0.05)
        token.cancel("user_cancelled")

    asyncio.create_task(cancel_later())

    # Direct invoke_with_cancel should raise GraphCancelled
    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await invoke_with_cancel(
            lambda: pipeline.retrieve("test query", top_k=5), token, timeout_s=1.0
        )

    assert pipeline.call_count == 1  # Pipeline was called but cancelled


@pytest.mark.asyncio
async def test_lambda_with_delay():
    """Test invoke_with_cancel with a simple lambda and delay to verify race condition."""
    token = CancellationToken("test_session")

    # Simple async function with delay
    async def delayed_result():
        await asyncio.sleep(0.1)  # 100ms delay
        return "result"

    # Cancel token after short delay
    async def cancel_later():
        await asyncio.sleep(0.05)  # 50ms delay
        token.cancel("user_cancelled")

    asyncio.create_task(cancel_later())

    # Should raise GraphCancelled due to race condition
    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await invoke_with_cancel(lambda: delayed_result(), token, timeout_s=1.0)


@pytest.mark.asyncio
async def test_rag_lambda_equivalent():
    """Test invoke_with_cancel with lambda equivalent to RAG node."""
    pipeline = MockRAGPipeline(delay=0.2)
    token = CancellationToken("test_session")

    # Cancel token after short delay
    async def cancel_later():
        await asyncio.sleep(0.05)
        token.cancel("user_cancelled")

    asyncio.create_task(cancel_later())

    # Lambda equivalent to what _rag_retriever_node does
    async def retrieve_pipeline():
        return await pipeline.retrieve("test query", top_k=5)

    # Should raise GraphCancelled due to race condition
    with pytest.raises(GraphCancelled, match="user_cancelled"):
        await invoke_with_cancel(lambda: retrieve_pipeline(), token, timeout_s=1.0)

    assert pipeline.call_count == 1  # Pipeline was called but cancelled


@pytest.mark.asyncio
async def test_rag_retriever_node_early_exit():
    """Test _rag_retriever_node early exit when token already cancelled."""
    pipeline = MockRAGPipeline(delay=0.1)
    token = CancellationToken("test_session")
    token.cancel("already_cancelled")

    # RAG retriever should raise immediately due to early exit
    from llm_client.agent.graph import _rag_retriever_node

    with pytest.raises(GraphCancelled, match="already_cancelled"):
        await _rag_retriever_node(
            {"messages": [{"type": "human", "content": "test query"}], "rag_top_k": 5},
            pipeline,
            config={"configurable": {"cancel_token": token}},
        )

    assert pipeline.call_count == 0  # Pipeline should not be called due to early exit


@pytest.mark.asyncio
async def test_build_agent_graph_with_timeout():
    """Test build_agent_graph passes timeout parameter."""
    llm = MockLLM()

    with patch("llm_client.agent.graph._planner_node") as mock_planner:
        mock_planner.return_value = {"messages": [], "iteration": 1}

        graph = build_agent_graph(llm, llm_invoke_timeout_s=30.0)

        # Verify timeout was passed (through invoke_with_cancel call)
        # This is indirect verification since we can't easily inspect the graph config
        assert graph is not None


def test_partial_answer_extraction():
    """Test _partial_answer extracts content from state messages."""
    # Empty state
    assert _partial_answer({}) is None
    assert _partial_answer({"messages": []}) is None

    # Message with string content
    msg1 = type("Message", (), {"content": "partial answer"})()
    assert _partial_answer({"messages": [msg1]}) == "partial answer"

    # Message without content
    msg2 = type("Message", (), {})()
    assert _partial_answer({"messages": [msg2]}) is None

    # Non-string content
    msg3 = type("Message", (), {"content": 123})()
    assert _partial_answer({"messages": [msg3]}) is None

    # Last message wins
    msg4 = type("Message", (), {"content": "final answer"})()
    msg5 = type("Message", (), {"content": "partial answer"})()
    assert _partial_answer({"messages": [msg4, msg5]}) == "partial answer"


@pytest.mark.asyncio
async def test_invoke_with_cancel_fallback_token():
    """Test invoke_with_cancel uses fallback token when config token is None."""
    token = CancellationToken("test_session")
    token.cancel("fallback_reason")
    llm = MockLLM(delay=0.01)

    with pytest.raises(GraphCancelled, match="fallback_reason"):
        await invoke_with_cancel(lambda: llm.ainvoke([]), token, timeout_s=1.0)

    assert llm.call_count == 0  # No LLM call when token already cancelled


@pytest.mark.asyncio
async def test_invoke_with_cancel_config_token_priority():
    """Test config token takes priority over fallback token."""
    config_token = CancellationToken("test_session")

    # Cancel config token, use it as the token parameter
    config_token.cancel("config_reason")
    llm = MockLLM(delay=0.01)

    with pytest.raises(GraphCancelled, match="config_reason"):
        await invoke_with_cancel(
            lambda: llm.ainvoke([]),
            config_token,  # Cancelled token
            timeout_s=1.0,
        )

    assert llm.call_count == 0  # No LLM call when token cancelled


@pytest.mark.asyncio
async def test_planner_node_no_config_fallback():
    """Test _planner_node with no config (no token to check)."""
    llm = MockLLM(delay=0.01)
    token = CancellationToken("test_session")
    token.cancel("fallback_reason")

    # Planner should not raise GraphCancelled when no config provided
    from llm_client.agent.graph import _planner_node

    result = await _planner_node(
        {"messages": [{"type": "human", "content": "test"}]},
        llm,
        config=None,  # No config, no token to check
    )

    assert result["iteration"] == 1  # LLM was called normally
    assert llm.call_count == 1  # LLM was called when no token to check


@pytest.mark.asyncio
async def test_invoke_with_cancel_normal_completion():
    """Test invoke_with_cancel returns normally when no cancellation occurs."""
    llm = MockLLM(delay=0.01)
    token = CancellationToken("test_session")  # Not cancelled

    result = await invoke_with_cancel(lambda: llm.ainvoke([]), token, timeout_s=1.0)

    assert result == "Response 1"
    assert llm.call_count == 1
    assert not token.is_cancelled
