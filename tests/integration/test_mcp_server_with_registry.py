"""Integration tests for McpServer + ExposedToolRegistry (H-2)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.llm_client.mcp.server import McpServer
from src.llm_client.mcp.tool_registry import (
    get_exposed_tool_registry,
    register_default_tools,
    reset_exposed_tool_registry,
)


def test_mcp_server_with_registry_returns_3_default_tools():
    """McpServer reads the 3 default tools from ExposedToolRegistry."""
    reset_exposed_tool_registry()
    try:
        register_default_tools()
        registry = get_exposed_tool_registry()

        app = FastAPI()
        server = McpServer(app, registry)
        server.mount()

        with TestClient(app) as client:
            response = client.get("/mcp/tools")
            assert response.status_code == 200
            data = response.json()
            assert len(data["tools"]) == 3
            names = {t["name"] for t in data["tools"]}
            assert names == {"rag_query", "file_export", "web_search"}
            for tool in data["tools"]:
                assert tool["description"]
                assert tool["args_schema"]

            response = client.get("/mcp/health")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ok"
            assert body["tools_count"] == 3
            assert set(body["tools"]) == names
    finally:
        reset_exposed_tool_registry()
