"""Unit tests for the agent_run MCP tool (BUG-BETA-04, BETA-PROMPTS H-1)."""

import inspect
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models import FakeListChatModel

from llm_client.mcp.agent_run import AgentRunArgs
from llm_client.mcp.server import McpServer
from llm_client.mcp.tool_registry import (
    build_default_tools,
    get_exposed_tool_registry,
    register_default_tools,
    reset_exposed_tool_registry,
)

FAKE_ANSWER = "Final answer from fake LLM"


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_exposed_tool_registry()
    yield
    reset_exposed_tool_registry()


def _patch_fake_llm(monkeypatch, response: str = FAKE_ANSWER) -> None:
    """Make LLMProviderFactory.create return a deterministic FakeListChatModel."""
    from llm_client.agent.provider import LLMProviderFactory

    def _create(*args, **kwargs):
        return FakeListChatModel(responses=[response])

    monkeypatch.setattr(LLMProviderFactory, "create", _create)


def _make_client() -> TestClient:
    register_default_tools()
    app = FastAPI()
    server = McpServer(app, get_exposed_tool_registry())
    server.mount()
    return TestClient(app)


def test_agent_run_in_default_tools():
    """build_default_tools exposes agent_run with a prompt schema and
    an async-generator handler (SSE streaming duck-typed in McpServer)."""
    tools = build_default_tools()
    names = [tool.name for tool in tools]
    assert names == ["rag_query", "file_export", "web_search", "agent_run"]

    agent_run = next(tool for tool in tools if tool.name == "agent_run")
    assert "prompt" in agent_run.args_schema["properties"]
    assert "max_iterations" in agent_run.args_schema["properties"]
    assert inspect.isasyncgenfunction(agent_run.handler)


def test_agent_run_args_schema_defaults():
    """AgentRunArgs defaults match the H-1 contract."""
    args = AgentRunArgs(prompt="do something")
    assert args.user_id == "anonymous"
    assert args.tools is None
    assert args.max_iterations == 10


def test_agent_run_stream_emits_progress_and_done(monkeypatch):
    """GET /mcp/tools/agent_run/stream yields tool_result progress chunks and a
    terminal done chunk carrying the final answer."""
    _patch_fake_llm(monkeypatch)

    with _make_client() as client:
        response = client.get(
            "/mcp/tools/agent_run/stream",
            params={"args_json": json.dumps({"prompt": "say hello"})},
        )

    assert response.status_code == 200
    body = response.text
    assert "event: tool_result" in body
    assert '"type": "progress"' in body
    assert '"type": "done"' in body
    assert FAKE_ANSWER in body

    data_chunks = [
        json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")
    ]
    types = [chunk.get("type") for chunk in data_chunks]
    assert "progress" in types
    assert "done" in types
    done = next(chunk for chunk in data_chunks if chunk.get("type") == "done")
    assert done["final_answer"] == FAKE_ANSWER
    assert done["session_id"]

    # Transport always terminates the stream with its own done event.
    assert "event: done" in body


def test_agent_run_post_returns_terminal_chunk(monkeypatch):
    """POST /mcp/tools/agent_run drains the generator and returns the terminal
    chunk as result (streamed=True marks the drain)."""
    _patch_fake_llm(monkeypatch)

    with _make_client() as client:
        response = client.post("/mcp/tools/agent_run", json={"prompt": "say hello"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["streamed"] is True
    assert payload["result"]["type"] == "done"
    assert payload["result"]["final_answer"] == FAKE_ANSWER


async def test_agent_run_handler_forwards_tools_and_max_iterations(monkeypatch):
    """tools=[] reaches resolve_tools (empty subset honoured) and
    max_iterations reaches the initial graph state."""
    from llm_client.agent import graph as graph_module
    from llm_client.agent import service as service_module
    from llm_client.mcp import agent_run as agent_run_module

    captured: dict = {}

    def _spy_resolve(request_settings):
        captured["request_settings"] = request_settings
        return []

    class _FakeGraph:
        async def astream(self, state):
            captured["state"] = state
            yield {"final_answer": {"final_answer": "ok", "messages": []}}

    def _fake_build(*args, **kwargs):
        return _FakeGraph()

    _patch_fake_llm(monkeypatch)
    monkeypatch.setattr(service_module, "resolve_tools", _spy_resolve)
    monkeypatch.setattr(graph_module, "build_agent_graph", _fake_build)

    chunks = [
        chunk
        async for chunk in agent_run_module.agent_run_handler(
            prompt="hi", tools=[], max_iterations=3
        )
    ]

    assert captured["request_settings"] == {"tools_enabled": []}
    assert captured["state"]["max_iterations"] == 3
    assert captured["state"]["messages"][0].content == "hi"
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["final_answer"] == "ok"


def test_agent_run_error_path(monkeypatch):
    """LLM construction failure surfaces as a terminal error chunk, not 500."""
    from llm_client.agent.provider import LLMProviderFactory

    def _boom(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(LLMProviderFactory, "create", _boom)

    with _make_client() as client:
        response = client.post("/mcp/tools/agent_run", json={"prompt": "hi"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    assert payload["result"]["type"] == "error"
    assert "provider unavailable" in payload["result"]["error"]
