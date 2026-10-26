"""Unit tests for McpServer (H-1)."""
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.llm_client.mcp.server import McpServer
from src.llm_client.mcp.tool_registry import reset_exposed_tool_registry


@pytest.fixture(autouse=True)
def _reset_singleton_registry():
    """McpServer falls back to the global ExposedToolRegistry singleton
    (H-2) — isolate tests from tools leaked by previous tests."""
    reset_exposed_tool_registry()
    yield
    reset_exposed_tool_registry()


def test_list_tools_returns_registered_tools():
    """Test GET /mcp/tools returns registered tools."""
    app = FastAPI()
    server = McpServer(app)
    
    server.register_tool(
        name="test_tool",
        description="Test tool",
        args_schema={"type": "object", "properties": {"foo": {"type": "string"}}},
        handler=AsyncMock(),
    )
    
    server.mount()
    
    with TestClient(app) as client:
        response = client.get("/mcp/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "test_tool"
        assert data["tools"][0]["description"] == "Test tool"


def test_call_tool_invokes_handler():
    """Test POST /mcp/tools/{name} invokes handler."""
    app = FastAPI()
    server = McpServer(app)
    
    async def mock_handler(foo: str, bar: int = 42) -> dict:
        return {"result": f"{foo}-{bar}"}
    
    server.register_tool(
        name="test_tool",
        description="Test tool",
        args_schema={"type": "object", "properties": {"foo": {"type": "string"}, "bar": {"type": "integer"}}},
        handler=mock_handler,
    )
    
    server.mount()
    
    with TestClient(app) as client:
        response = client.post("/mcp/tools/test_tool", json={"foo": "hello", "bar": 123})
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["result"] == "hello-123"
        assert data["error"] is None


def test_call_tool_unknown_returns_404():
    """Test POST /mcp/tools/unknown returns 404."""
    app = FastAPI()
    server = McpServer(app)
    server.mount()
    
    with TestClient(app) as client:
        response = client.post("/mcp/tools/unknown", json={"foo": "bar"})
        assert response.status_code == 404


def test_call_tool_handler_error_returns_error_dict():
    """Test handler error returns {error: "..."} instead of 500."""
    app = FastAPI()
    server = McpServer(app)
    
    async def failing_handler():
        raise ValueError("Test error")
    
    server.register_tool(
        name="failing_tool",
        description="Failing tool",
        args_schema={"type": "object"},
        handler=failing_handler,
    )
    
    server.mount()
    
    with TestClient(app) as client:
        response = client.post("/mcp/tools/failing_tool", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["result"] is None
        assert "Test error" in data["error"]


def test_streaming_endpoint_emits_sse_events():
    """Test GET /mcp/tools/{name}/stream emits SSE events."""
    app = FastAPI()
    server = McpServer(app)
    
    async def streaming_handler(query: str):
        for i in range(3):
            yield {"chunk": f"result {i}"}
    
    server.register_tool(
        name="streaming_tool",
        description="Streaming tool",
        args_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=streaming_handler,
    )
    
    server.mount()
    
    with TestClient(app) as client:
        response = client.get("/mcp/tools/streaming_tool/stream?args_json={\"query\": \"test\"}")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                events.append(data)
        
        assert len(events) == 3
        assert events[0]["chunk"] == "result 0"
        assert events[1]["chunk"] == "result 1"
        assert events[2]["chunk"] == "result 2"


def test_health_endpoint_returns_status():
    """Test GET /mcp/health returns server status."""
    app = FastAPI()
    server = McpServer(app)
    
    server.register_tool("test", "desc", {}, AsyncMock())
    server.mount()
    
    with TestClient(app) as client:
        response = client.get("/mcp/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["tools_count"] == 1
        assert data["tools"] == ["test"]


def test_mcp_mounted_only_when_enabled():
    """Test MCP routes only exist when enabled."""
    # Test with disabled MCP
    app1 = FastAPI()
    with TestClient(app1) as client:
        response = client.get("/mcp/tools")
        assert response.status_code == 404
    
    # Test with enabled MCP
    app2 = FastAPI()
    server2 = McpServer(app2)
    server2.register_tool("test", "desc", {}, AsyncMock())
    server2.mount()
    
    with TestClient(app2) as client:
        response = client.get("/mcp/tools")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tools"]) == 1


def test_invalid_args_json_returns_400():
    """Test invalid JSON args returns 400."""
    app = FastAPI()
    server = McpServer(app)
    
    server.register_tool("test", "desc", {}, AsyncMock())
    server.mount()
    
    with TestClient(app) as client:
        response = client.get("/mcp/tools/test/stream?args_json={invalid json}")
        assert response.status_code == 400
        assert "Invalid args JSON" in response.json()["detail"]


def test_large_args_json_accepted():
    """Test large args JSON is accepted (FastAPI doesn't enforce 4KB limit by default)."""
    app = FastAPI()
    server = McpServer(app)
    
    async def mock_handler(data: str):
        return {"length": len(data)}
    
    server.register_tool("test", "desc", {}, mock_handler)
    server.mount()
    
    # Create 5KB JSON string
    large_json = json.dumps({"data": "x" * 5000})
    
    with TestClient(app) as client:
        response = client.get(f"/mcp/tools/test/stream?args_json={large_json}")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        # Parse SSE events
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                events.append(data)
        
        assert len(events) == 1
        assert events[0]["length"] == 5000