"""Integration tests for MCP Server probe (H-4)."""
import asyncio
import importlib.util
import logging
from pathlib import Path

import httpx
import pytest

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.integration


# Load probe script module (robust import without package assumptions)
PROBE_SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "probe_mcp_server.py"
probe_spec = importlib.util.spec_from_file_location("probe_mcp_server", PROBE_SCRIPT_PATH)
probe_module = importlib.util.module_from_spec(probe_spec)
probe_spec.loader.exec_module(probe_module)


# No MockTransport needed - directly patch httpx.AsyncClient.get/post methods


def test_probe_passes_when_server_healthy(monkeypatch):
    """Probe passes when server responds correctly to all endpoints."""
    call_count = 0
    
    async def mock_response(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        if call_count == 1:  # Health check
            return httpx.Response(200, json={"status": "ok", "tools_count": 3, "tools": ["rag_query", "file_export", "web_search"]})
        elif call_count == 2:  # List tools
            return httpx.Response(200, json={
                "tools": [
                    {"name": "rag_query", "description": "RAG query tool", "args_schema": {"type": "object"}},
                    {"name": "file_export", "description": "File export tool", "args_schema": {"type": "object"}},
                    {"name": "web_search", "description": "Web search tool", "args_schema": {"type": "object"}},
                ]
            })
        elif call_count <= 5:  # Tool calls (3 tools)
            return httpx.Response(200, json={"result": {"success": True}, "error": None})
        elif call_count == 6:  # Stream
            return httpx.Response(200, content="event: tool_result\ndata: {\"chunk\": \"test\"}\n\nevent: done\ndata: {}\n\n", headers={"content-type": "text/event-stream"})
        else:
            raise ValueError(f"Unexpected call #{call_count}")
    
    
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_response)
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_response)
    
    result = asyncio.run(probe_module.probe_mcp_server("http://test"))
    assert result is True


def test_probe_fails_on_health_check_failure(monkeypatch):
    """Probe fails when /mcp/health returns 500."""
    async def mock_health_check_500(*args, **kwargs):
        return httpx.Response(500, json={"error": "Internal error"})
    
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_health_check_500)
    
    result = asyncio.run(probe_module.probe_mcp_server("http://test"))
    assert result is False


def test_probe_fails_on_list_tools_failure(monkeypatch):
    """Probe fails when /mcp/tools returns 500."""
    async def mock_health(*args, **kwargs):
        return httpx.Response(200, json={"status": "ok", "tools_count": 3, "tools": ["rag_query", "file_export", "web_search"]})
    
    async def mock_tools_500(*args, **kwargs):
        return httpx.Response(500, json={"error": "List tools failed"})
    
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_health)
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_tools_500)
    
    result = asyncio.run(probe_module.probe_mcp_server("http://test"))
    assert result is False


def test_probe_passes_with_tool_errors(monkeypatch):
    """Probe passes even when tools return errors (non-critical)."""
    call_count = 0
    
    async def mock_response(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        if call_count == 1:  # Health check
            return httpx.Response(200, json={"status": "ok", "tools_count": 3, "tools": ["rag_query", "file_export", "web_search"]})
        elif call_count == 2:  # List tools
            return httpx.Response(200, json={
                "tools": [
                    {"name": "rag_query", "description": "RAG query", "args_schema": {"type": "object"}},
                    {"name": "file_export", "description": "File export", "args_schema": {"type": "object"}},
                    {"name": "web_search", "description": "Web search", "args_schema": {"type": "object"}},
                ]
            })
        elif call_count == 3:  # rag_query (success)
            return httpx.Response(200, json={"result": {"chunks": ["test"]}, "error": None})
        elif call_count == 4:  # file_export (success)
            return httpx.Response(200, json={"result": {"path": "/tmp/test.txt"}, "error": None})
        elif call_count == 5:  # web_search (error)
            return httpx.Response(200, json={"result": None, "error": "TAVILY_API_KEY missing"})
        elif call_count == 6:  # SSE stream
            return httpx.Response(200, content="event: tool_result\ndata: {\"chunk\": \"test\"}\n\nevent: done\ndata: {}\n\n", headers={"content-type": "text/event-stream"})
        else:
            raise ValueError(f"Unexpected call #{call_count}")
    
    
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_response)
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_response)
    
    result = asyncio.run(probe_module.probe_mcp_server("http://test"))
    assert result is True


def test_get_minimal_args_per_tool():
    """Test get_minimal_args returns correct minimal args for each known tool."""
    # Test known tools
    assert probe_module.get_minimal_args("rag_query") == {"query": "test", "top_k": 1}
    assert probe_module.get_minimal_args("file_export") == {"filename": "test.txt", "content": "test"}
    assert probe_module.get_minimal_args("web_search") == {"query": "test", "max_results": 1}
    
    # Test unknown tool
    assert probe_module.get_minimal_args("unknown_tool") == {}