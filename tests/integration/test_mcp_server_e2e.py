"""Integration tests for McpServer e2e."""
import json
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.llm_client.agent.service import create_agent_app
from src.llm_client.config import settings


async def test_mcp_server_e2e():
    """Full end-to-end MCP server test with real FastAPI app."""
    # Override MCP flag for test
    original_mcp_enabled = settings.mcp_server_enabled
    settings.mcp_server_enabled = True
    
    try:
        app = create_agent_app()
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test list tools
            response = await client.get("/mcp/tools")
            assert response.status_code == 200
            data = response.json()
            assert len(data["tools"]) == 3
            tool_names = [t["name"] for t in data["tools"]]
            assert "rag_query" in tool_names
            assert "file_export" in tool_names
            assert "web_search" in tool_names
            
            # Test rag_query tool
            response = await client.post(
                "/mcp/tools/rag_query",
                json={"query": "test query", "top_k": 5}
            )
            assert response.status_code == 200
            result = response.json()
            assert "chunks" in result
            assert "chunk_count" in result
            
            # Test web_search tool (mock TAVILY_API_KEY in conftest)
            response = await client.post(
                "/mcp/tools/web_search",
                json={"query": "python asyncio", "max_results": 3}
            )
            assert response.status_code == 200
            result = response.json()
            assert isinstance(result, list)
            if result:  # If search returns results
                assert "title" in result[0]
                assert "url" in result[0]
                assert "snippet" in result[0]
            
            # Test file_export tool
            response = await client.post(
                "/mcp/tools/file_export",
                json={"content": "test content", "format": "txt", "filename": "test.txt"}
            )
            assert response.status_code == 200
            result = response.json()
            assert "artifact_id" in result
            assert "format" in result
            assert result["format"] == "txt"
            
            # Test health endpoint
            response = await client.get("/mcp/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["tools_count"] == 3
            
    finally:
        # Restore original setting
        settings.mcp_server_enabled = original_mcp_enabled