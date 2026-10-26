"""Integration tests for McpServer e2e."""

from httpx import ASGITransport, AsyncClient

from src.llm_client.agent.service import create_agent_app
from src.llm_client.config import settings
from src.llm_client.mcp.tool_registry import reset_exposed_tool_registry


async def test_mcp_server_e2e():
    """Full end-to-end MCP server test with real FastAPI app."""
    # Override MCP flag for test
    original_mcp_enabled = settings.mcp_server_enabled
    settings.mcp_server_enabled = True
    reset_exposed_tool_registry()

    try:
        app = create_agent_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test list tools
            response = await client.get("/mcp/tools")
            assert response.status_code == 200
            data = response.json()
            assert len(data["tools"]) == 3
            tool_names = [t["name"] for t in data["tools"]]
            assert "rag_query" in tool_names
            assert "file_export" in tool_names
            assert "web_search" in tool_names

            # Test rag_query tool — MCP call_tool wraps output in {result, error}
            response = await client.post(
                "/mcp/tools/rag_query", json={"query": "test query", "top_k": 5}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["error"] is None
            assert "chunks" in body["result"]
            assert "chunk_count" in body["result"]

            # Test web_search tool (TAVILY_API_KEY is a placeholder in
            # conftest — backend errors surface as {result: null, error}
            # and are acceptable here; the MCP contract is what matters)
            response = await client.post(
                "/mcp/tools/web_search", json={"query": "python asyncio", "max_results": 3}
            )
            assert response.status_code == 200
            body = response.json()
            if body["error"] is None:
                assert isinstance(body["result"], list)
                if body["result"]:
                    assert "title" in body["result"][0]
                    assert "url" in body["result"][0]
                    assert "snippet" in body["result"][0]
            else:
                assert body["result"] is None
                assert isinstance(body["error"], str)

            # Test file_export tool (MinIO may be unavailable without
            # docker-compose — same contract-tolerant check)
            response = await client.post(
                "/mcp/tools/file_export",
                json={"content": "test content", "format": "txt", "filename": "test.txt"},
            )
            assert response.status_code == 200
            body = response.json()
            if body["error"] is None:
                assert "artifact_id" in body["result"]
                assert "format" in body["result"]
                assert body["result"]["format"] == "txt"
            else:
                assert body["result"] is None
                assert isinstance(body["error"], str)

            # Test health endpoint
            response = await client.get("/mcp/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["tools_count"] == 3

    finally:
        # Restore original setting
        settings.mcp_server_enabled = original_mcp_enabled
        reset_exposed_tool_registry()
